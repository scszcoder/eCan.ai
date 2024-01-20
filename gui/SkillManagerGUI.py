from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel, QPalette
from PySide6.QtWidgets import QApplication, QMainWindow, QTableView, QPushButton, QVBoxLayout, QWidget, QTextEdit
from PySide6.QtCore import QModelIndex, QItemSelection, QItemSelectionModel, QPropertyAnimation, QAbstractAnimation, QParallelAnimationGroup, QAbstractTableModel
from PySide6.QtGui import QMouseEvent, QPainter
from PySide6.QtWidgets import QStyledItemDelegate, QStyle, QToolButton, QItemDelegate, QHeaderView

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
            pixmap = icon.pixmap(QSize(32, 32))  # Adjust the size as needed
            painter.drawPixmap(option.rect, pixmap)


class SkillCellDelegate(QItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        print("PARENT USER:::", self.parent.user)

    def createEditor(self, parent, option, index):
        # Check if the cell should be editable based on your criteria
        print("PARENT USER:", self.parent.user)
        if index.column() == 2 and index.data() != self.parent.user:
            return None  # Return None to make the cell non-editable
        else:
            return super().createEditor(parent, option, index)

class NonEditableItemDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter, option, index):
        # Check if the item is not editable
        if not index.model().itemFromIndex(index).isEditable():
            option.state &= ~QStyle.State_Enabled
            option.state &= ~QStyle.State_ReadOnly

        super().paint(painter, option, index)

class SkillTableModel(QAbstractTableModel):
    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.data = data if data is not None else []
        self.parent = parent

    def rowCount(self, parent=None):
        return len(self.data)

    def columnCount(self, parent=None):
        if self.data:
            return len(self.data[0])
        return 0

    def data(self, index, role):
        if not index.isValid():
            return None
        elif role == Qt.DisplayRole:
            return self.data[index.row()][index.column()]
        elif role == Qt.DecorationRole and index.column() == 7:
            # Set an icon for the 7th column based on the value in the 2nd column
            column_2_value = self.data[index.row()][2]
            if column_2_value == "PUB":
                pixmap = QPixmap(self.parent.getHomePath() + '/resource/images/icons/skills_78.png')  # Replace with the path to your icon image
            elif column_2_value == "PRV":
                pixmap = QPixmap(self.parent.getHomePath() + '/resource/images/icons/private_skills_78.png')  # Replace with the path to another icon image
            elif column_2_value == "PPU":
                pixmap = QPixmap(self.parent.getHomePath() + '/resource/images/icons/private_usable_skills_78.png')  # No icon if no match
            else:
                pixmap = QPixmap()  # No icon if no match
            return pixmap


    def flags(self, index):
        flags = super().flags(index)
        if index.column() == 2 and self.data[index.row()][index.column()] == self.parent.user:
            flags &= ~Qt.ItemIsEditable  # Remove the editable flag for column 6 cells
        return flags

    def addRow(self, new_data):
        self.beginInsertRows(self.index(len(self.data), 0), len(self.data), len(self.data))
        self.data.append(new_data)
        self.endInsertRows()

    def updateData(self, row, column, new_value):
        self.data[row][column] = new_value
        self.dataChanged.emit(self.index(row, column), self.index(row, column))

    def clearTable(self):
        self.beginRemoveRows(QModelIndex(), 0, len(self.data) - 1)
        self.data.clear()
        self.endRemoveRows()

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
        self.headerLine =  QFrame()
        self.toggleButton = QToolButton()
        self.mainLayout = QGridLayout()

        toggleButton = self.toggleButton
        toggleButton.setStyleSheet("QToolButton { border: none; }")
        toggleButton.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toggleButton.setArrowType(Qt.RightArrow)
        toggleButton.setText(str(title))
        toggleButton.setCheckable(True)
        toggleButton.setChecked(True)

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

        def start_animation(checked):
            arrow_type = Qt.DownArrow if checked else Qt.RightArrow
            direction = QAbstractAnimation.Forward if checked else QAbstractAnimation.Backward
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

class SkillTableView(QTableView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setMouseTracking(True)
        self.start_index = None
        self.setItemDelegate(NonEditableItemDelegate(self))
        self.setSelectionBehavior(QTableView.SelectRows)


    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            print("ENTER PRESSED!!!!")
            current_index = self.currentIndex()
            if current_index.isValid() and self.isEditValid():
                editor = self.focusWidget()
                if editor:
                    new_value = editor.text()
                    self.model().setData(current_index, new_value, Qt.EditRole)
        else:
            super().keyPressEvent(event)

    def isEditValid(self):
        editor = self.focusWidget()
        if editor:
            text = editor.text()
            return text.strip() != ""  # Check if the edited text is not empty
        return False

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.start_index = self.indexAt(event.pos())
            print("Clicked ON:", self.start_index.row())
            if self.start_index.isValid():
                self.clearSelection()  # Clear previous selections
                self.selectionModel().setCurrentIndex(self.start_index, QItemSelectionModel.Select)
            selected_skill = self.findSkillById(int(self.parent.skillModel.item(self.start_index.row(), 0).text()))
            # print("SELECTED SKID:", int(self.parent.skillModel.item(self.start_index.row(), 0).text()), "::", selected_skill.getDescription(), "!")
            self.parent.skillInfoConsole.setText(selected_skill.getDescription())
        super().mousePressEvent(event)

    def findSkillById(self, skid):
        return next((x for x in self.parent.parent.skills if x.getSkid() == skid), None)

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.LeftButton and self.start_index:
            end_index = self.indexAt(event.pos())
            if end_index.isValid():
                selection_model = self.selectionModel()
                selection = QItemSelection(self.start_index, end_index)
                selection_model.select(selection, QItemSelectionModel.Select)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.start_index = None
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        # Call the base class paintEvent to draw the table view
        super().paintEvent(event)

        # Custom painting for non-editable cells that are selected
        if self.start_index:
            painter = QPainter(self.viewport())
            selection_model = self.selectionModel()
            selected_indexes = selection_model.selectedIndexes()

            palette = self.palette()
            highlight_color = palette.color(QPalette.Highlight)

            for index in selected_indexes:
                if not self.model().itemFromIndex(index).isEditable():
                    rect = self.visualRect(index)
                    painter.fillRect(rect, highlight_color)


# class MainWindow(QWidget):
class SkillManagerWindow(QMainWindow):
    def __init__(self, parent, entrance="msg"):
        super(SkillManagerWindow, self).__init__()
        self.parent = parent
        self.mainWidget = QWidget()
        self.skills = []
        self.show_all_local_button = QPushButton(QApplication.translate("QPushButton", "Show All"))
        self.show_all_local_button.clicked.connect(self.showAllLocalSkills)

        self.fetch_mine_button = QPushButton(QApplication.translate("QPushButton", "Fetch All Mine"))
        self.fetch_mine_button.clicked.connect(self.fetchMySkills)

        self.search_skill_button = QPushButton(QApplication.translate("QPushButton", "Search Skills"))
        self.search_skill_button.clicked.connect(self.searchSkills)

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
        self.skill_search_edit.returnPressed.connect(self.search_skill_button.click)


        font = QFont("Arial", 10)

        self.centralScroll = QScrollArea()
        self.centralScroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.centralScroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.centralScroll.setWidgetResizable(True)

        self.skillTableView = SkillTableView(self)

        header = self.skillTableView.horizontalHeader()
        header.setFont(font)
        header.setSectionResizeMode(QHeaderView.ResizeToContents)

        # self.skillModel = SkillTableModel(self.parent)
        self.skillModel = QStandardItemModel(0, 8)
        self.skillModel.setHorizontalHeaderLabels(['Skill ID', 'Name', 'Owner', 'Users', 'Created On', 'Privacy', 'Platform_App_Site_page', ''])
        self.skillTableView.setModel(self.skillModel)

        i = 0
        print("skills:::", len(self.parent.skills))
        # self.fillTable()

        # Replace "Arial" and 12 with your desired font family and size
        self.skillTableView.resizeColumnsToContents()
        # self.skillTableView.setColumnWidth(7, 256)
        self.skillTableView.setFont(font)
        self.skillTableView.installEventFilter(self)
        # column 6 could be either an icon or an animating gif....
        self.skillTableView.setItemDelegateForColumn(7, IconDelegate())
        # completedMissionTableView.setItemDelegateForColumn(6, MovieDelegate())
        # self.skillTableView.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.skillTableView.doubleClicked.connect(self.handleRowDoubleClick)


        delegate = SkillCellDelegate(self.parent)
        self.skillTableView.setItemDelegate(delegate)

        self.infoConsoleBox = Expander(self, QApplication.translate("QWidget", "Skill Info Console:"))
        self.skillInfoConsole = QTextEdit()
        # self.skillInfoConsole.setLineWrapMode(QTextEdit.FixedPixelWidth)
        self.skillInfoConsole.setLineWrapMode(QTextEdit.WidgetWidth)
        # self.skillInfoConsole.autoFormatting()
        self.skillInfoConsole.verticalScrollBar().setValue(self.skillInfoConsole.verticalScrollBar().minimum())
        self.infoConsoleLayout = QVBoxLayout()
        self.infoConsoleLayout.addWidget(self.skillInfoConsole)

        self.infoConsoleBox.setContentLayout(self.infoConsoleLayout)

        self.centralScroll.setWidget(self.skillTableView)
        self.sm_layout.addWidget(self.centralScroll)
        self.tp_layout.addWidget(self.fetch_mine_button)
        self.tp_layout.addWidget(self.skill_search_edit)
        self.tp_layout.addWidget(self.show_all_local_button)
        self.layout.addLayout(self.tp_layout)
        self.layout.addLayout(self.sm_layout)
        self.layout.addWidget(self.infoConsoleBox)


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

    def handleRowDoubleClick(self, index):
        this_skill = next((x for x in self.parent.skills if x.getSkid() == int(self.skillModel.item(index.row(), 0).text())), None)
        # now open this skill in skill editor and populate all, but make save skill button grayed out and disabled.


    # this function search all local skills by search phrase. it will search thru platform app site page name description field for any match.
    # after search, the search result will be displayed in the table.
    def searchSkills(self):
        matched_idxs = []
        sphrases = self.skill_search_edit.text().split()
        for skidx in range(len(self.parent.skills)):
            for sphrase in sphrases:
                if (sphrase in self.parent.skills[skidx].getName()) or \
                    (sphrase in self.parent.skills[skidx].getPlatform()) or \
                    (sphrase in self.parent.skills[skidx].getApp()) or \
                    (sphrase in self.parent.skills[skidx].getSite()) or \
                    (sphrase in self.parent.skills[skidx].getPage()) or \
                    (sphrase in self.parent.skills[skidx].getDescription()):
                    matched_idxs.append(skidx)
                    break

        print("search result indexs:", matched_idxs)
        self.search_result_skills = [self.parent.skills[idx] for idx in matched_idxs]
        self.skillModel.clear()
        self.updateSkills(self.search_result_skills)



    def updateSkills(self, skillData):
        i = 0
        for sk in skillData:
            self.fill1TableRow(i, skillData, self.skillModel)
            self.skillTableView.setRowHeight(i, 32)
            i = i + 1

    def showAllLocalSkills(self):
        self.skillModel.clear()
        self.updateSkills(self.parent.skills)

    def showSearchResultSkills(self):
        self.skillModel.clear()
        self.updateSkills(self.searchResultSkills)

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
        items = []
        text_item = QStandardItem(str(rowData[rowIdx].getSkid()))
        model.setItem(rowIdx, 0, text_item)
        items.append(text_item)

        text_item = QStandardItem(rowData[rowIdx].getName())
        model.setItem(rowIdx, 1, text_item)
        items.append(text_item)

        text_item = QStandardItem(rowData[rowIdx].getOwner())
        model.setItem(rowIdx, 2, text_item)
        items.append(text_item)

        # text_item = QStandardItem(rowData[rowIdx].getUsers())
        text_item = QStandardItem(rowData[rowIdx].getOwner())
        model.setItem(rowIdx, 3, text_item)
        items.append(text_item)

        text_item = QStandardItem(rowData[rowIdx].getCreatedOn())
        model.setItem(rowIdx, 4, text_item)
        items.append(text_item)

        text_item = QStandardItem(rowData[rowIdx].getPrivacy())
        model.setItem(rowIdx, 5, text_item)
        items.append(text_item)

        pasp = rowData[rowIdx].getPlatform() + "_" + rowData[rowIdx].getApp() + "_" + rowData[rowIdx].getSite() + "_" + rowData[rowIdx].getPage()
        text_item = QStandardItem(pasp)
        model.setItem(rowIdx, 6, text_item)
        items.append(text_item)

        icon_item = QStandardItem()
        if rowData[rowIdx].getPrivacy() == "PUB":
            icon_item.setIcon(QIcon(self.parent.getHomePath() + '/resource/images/icons/skills_78.png'))
            icon_item.setSizeHint(QSize(32, 32))
            model.setItem(rowIdx, 7, icon_item)
        elif rowData[rowIdx].getPrivacy() == "PRV":
            icon_item.setIcon(QIcon(self.parent.getHomePath() + '/resource/images/icons/private_skills_78.png'))
            icon_item.setSizeHint(QSize(32, 32))
            model.setItem(rowIdx, 7, icon_item)
        else:
            icon_item.setIcon(QIcon(self.parent.getHomePath() + '/resource/images/icons/private_usable_skills_78.png'))
            icon_item.setSizeHint(QSize(32, 32))
            model.setItem(rowIdx, 7, icon_item)
        items.append(icon_item)

        if (rowData[rowIdx].getOwner() != self.parent.user):
            for item in items:
                # item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                item.setFlags(item.flags() | Qt.ItemIsSelectable)



    def fillTable(self):
        i = 0
        self.addColTitleRow()
        for sk in self.parent.skills:
            print("FILL ADD 1 ROW...", i)
            self.add1TableRow(i, self.parent.skills)
            self.skillTableView.setRowHeight(i, 32)
            i = i + 1

    def addColTitleRow(self):
        new_data = ['Skill ID', 'Name', 'Owner', 'Users', 'Created On', 'Privacy', 'Platform/App/Site/page', '']
        self.skillModel.addRow(new_data)

    def add1TableRow(self, rowIdx, rowData):
        new_data = [str(rowData[rowIdx].getSkid()), rowData[rowIdx].getName(), rowData[rowIdx].getOwner(), rowData[rowIdx].getOwner(), rowData[rowIdx].getCreatedOn(), rowData[rowIdx].getPrivacy(), rowData[rowIdx].getPlatform()+"/"+rowData[rowIdx].getApp()+"/"+rowData[rowIdx].getSite()+"/"+rowData[rowIdx].getPage()]
        print("New ROW:", new_data)
        self.skillModel.addRow(new_data)


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
        # print("Source:", source, "Event:", event)
        if event.type() == QEvent.ContextMenu and source is self.skillTableView:
            # print("skill menu....")
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
            # print("selected:", selected_act)

            if selected_act:
                self.selected_skill_row = source.rowAt(event.pos().y())
                # print("selected row:", self.selected_skill_row)
                if self.selected_skill_row == -1:
                    self.selected_skill_row = source.model().rowCount() - 1
                self.selected_skill_column = source.columnAt(event.pos().x())
                if self.selected_skill_column == -1:
                    self.selected_skill_column = source.model().columnCount() - 1

                # print("selected col :", self.selected_skill_column)
                self.selected_skill_item = self.skillModel.item(self.selected_skill_row)
                # print("selected item1 :", self.selected_skill_item)

                skill_idx = self.skillTableView.index(source)
                # print("selected Skill_idx :", skill_idx)

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
        # print("fetch skills results:", resp)
        return resp


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