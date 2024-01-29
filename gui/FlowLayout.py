from PySide6.QtCore import QSize, QRect, QPoint, Qt, QItemSelectionModel
from PySide6.QtGui import QStandardItem, QIcon, QAction, QCursor, QMouseEvent
from PySide6.QtWidgets import QListView, QMenu, QFrame, QLayout, QLabel, QSizePolicy


class BotListView(QListView):
    def __init__(self, parent=None):
        super(BotListView, self).__init__()
        self.parent = parent


    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.parent.selected_bot_row = self.indexAt(event.pos()).row()
            self.parent.selected_bot_item = self.parent.botModel.item(self.parent.selected_bot_row)
            print("clicked")
        super().mousePressEvent(event)

class MissionListView(QListView):
    def __init__(self, parent=None):
        super(MissionListView, self).__init__()
        self.parent = parent

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.parent.selected_mission_row = self.indexAt(event.pos()).row()
            self.parent.selected_mission_row = self.parent.missionModel.item(self.parent.selected_mission_row)
        super().mousePressEvent(event)

class VehicleListView(QListView):
    def __init__(self, parent=None):
        super(VehicleListView, self).__init__()
        self.parent = parent

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.parent.selected_vehicle_row = self.indexAt(event.pos()).row()
            self.parent.selected_cus_mission_item = self.parent.runningVehicleModel.item(self.parent.selected_vehicle_row)
        super().mousePressEvent(event)

class BotView(QStandardItem):
    def __init__(self, homepath):
        super(BotView, self).__init__()
        self.setText('bot0')
        self.homepath = homepath
        self.bot0Icon = QIcon(homepath+'/resource/images/icons/c_robot64_0.png')
        self.bot0.setIcon(self.bot0Icon)
        self.popMenu = QMenu(self)
        self.popMenu.addAction(QAction('Edit', self))
        self.popMenu.addAction(QAction('Clone', self))
        self.popMenu.addSeparator()
        self.popMenu.addAction(QAction('Delete', self))

    # def contextMenuEvent(self, event):
    #     # add other required actions
    #     self.popMenu.popup(QCursor.pos())

class DragIcon(QLabel):

    def install_rc_menu(self):
        # create context menu
        self.popMenu = QMenu(self)
        self.popMenu.addAction(QAction('Edit', self))
        self.popMenu.addAction(QAction('Clone', self))
        self.popMenu.addSeparator()
        self.popMenu.addAction(QAction('Delete', self))

    def on_context_menu(self, point):
        # show context menu
        self.popMenu.exec_(self.button.mapToGlobal(point))

    def mousePressEvent(self, event):
        self.__mousePressPos = None
        self.__mouseMovePos = None
        if event.button() == Qt.LeftButton:
            self.__mousePressPos = event.globalPos()
            self.__mouseMovePos = event.globalPos()

        super(DragIcon, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            # adjust offset from clicked point to origin of widget
            currPos = self.mapToGlobal(self.pos())
            globalPos = event.globalPos()
            diff = globalPos - self.__mouseMovePos
            newPos = self.mapFromGlobal(currPos + diff)
            self.move(newPos)

            self.__mouseMovePos = globalPos

        super(DragIcon, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.__mousePressPos is not None:
            moved = event.globalPos() - self.__mousePressPos
            if moved.manhattanLength() > 3:
                event.ignore()
                return

        super(DragIcon, self).mouseReleaseEvent(event)

    def clicked(self):
        print("click as normal!")

    def contextMenuEvent(self, event):
        # add other required actions
        self.popMenu.popup(QCursor.pos())


class DragPanel(QFrame):
    def __init__(self):
        super(DragPanel, self).__init__()

        self.flowLayout = FlowLayout()
        #flowLayout.addWidget(QLabel("Short"))
        self.setLayout(self.flowLayout)

    def addBot(self, bot):
        self.flowLayout.addWidget(bot)


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, spacing=-1):
        super(FlowLayout, self).__init__(parent)

        if parent is not None:
            self.setMargin(margin)

        self.setSpacing(spacing)

        self.itemList = []

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self.itemList.append(item)

    def count(self):
        return len(self.itemList)

    def itemAt(self, index):
        if index >= 0 and index < len(self.itemList):
            return self.itemList[index]

        return None

    def takeAt(self, index):
        if index >= 0 and index < len(self.itemList):
            return self.itemList.pop(index)

        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self.doLayout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super(FlowLayout, self).setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()

        for item in self.itemList:
            size = size.expandedTo(item.minimumSize())

        size += QSize(2 * self.contentsMargins().top(), 2 * self.contentsMargins().top())
        return size

    def doLayout(self, rect, testOnly):
        x = rect.x()
        y = rect.y()
        lineHeight = 0

        for item in self.itemList:
            # wid = item.widget()
            # spaceX = self.spacing() + wid.QStyle().layoutSpacing(QSizePolicy.Label, QSizePolicy.Label, Qt.Horizontal)
            # spaceY = self.spacing() + wid.QStyle().layoutSpacing(QSizePolicy.Label, QSizePolicy.Label, Qt.Vertical)

            spaceX = self.spacing() + item.wid.style().layoutSpacing(QSizePolicy.Label, QSizePolicy.Label, Qt.Horizontal)
            spaceY = self.spacing() + item.wid.style().layoutSpacing(QSizePolicy.Label, QSizePolicy.Label, Qt.Vertical)
            nextX = x + item.sizeHint().width() + spaceX
            if nextX - spaceX > rect.right() and lineHeight > 0:
                x = rect.x()
                y = y + lineHeight + spaceY
                nextX = x + item.sizeHint().width() + spaceX
                lineHeight = 0

            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())

        return y + lineHeight - rect.y()
