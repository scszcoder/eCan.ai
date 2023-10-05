from PySide6 import QtCore, QtGui, QtWidgets

class BotListView(QtWidgets.QListView):
    def __init__(self):
        super(BotListView, self).__init__()
        # self.popMenu = QtWidgets.QMenu(self)
        # self.popMenu.addAction(self._createBotRCEditAction())
        # self.popMenu.addAction(self._createBotRCCloneAction())
        # self.popMenu.addSeparator()
        # self.popMenu.addAction(self._createBotRCDeleteAction())

    # def eventFilter(self, source, event):
    #     if event.type() == QtCore.QEvent.ContextMenu and source is self:
    #         self.popMenu = QtWidgets.QMenu(self)
    #         self.popMenu.addAction(self._createBotRCEditAction())
    #         self.popMenu.addAction(self._createBotRCCloneAction())
    #         self.popMenu.addSeparator()
    #         self.popMenu.addAction(self._createBotRCDeleteAction())
    #
    #         if self.popMenu.exec_(event.globalPos()):
    #             item = source.itemAt(event.pos())
    #             print(item.text())
    #         return True
    #     return super().eventFilter(source, event)

    # def contextMenuEvent(self, event):
    #     # add other required actions
    #     self.popMenu.popup(QtGui.QCursor.pos())

    # def _createBotRCEditAction(self):
    #     # File actions
    #     new_action = QtGui.QAction(self)
    #     new_action.setText("&Edit")
    #     new_action.triggered.connect(self.editBot)
    #     return new_action
    #
    # def _createBotRCCloneAction(self):
    #     # File actions
    #     new_action = QtGui.QAction(self)
    #     new_action.setText("&Clone")
    #     new_action.triggered.connect(self.cloneBot)
    #     return new_action
    #
    # def _createBotRCDeleteAction(self):
    #     # File actions
    #     new_action = QtGui.QAction(self)
    #     new_action.setText("&Delete")
    #     new_action.triggered.connect(self.deleteBot)
    #     return new_action
    #
    # def editBot(self):
    #     # File actions
    #     print("edit bot")
    #
    # def cloneBot(self):
    #     # File actions
    #     print("clone bot")
    #
    # def deleteBot(self):
    #     # File actions
    #     print("delete bot")

class MissionListView(QtWidgets.QListView):
    def __init__(self):
        super(MissionListView, self).__init__()
    #     self.popMenu = QtWidgets.QMenu(self)
    #     self.popMenu.addAction(QtGui.QAction('Edit', self))
    #     self.popMenu.addAction(QtGui.QAction('Clone', self))
    #     self.popMenu.addSeparator()
    #     self.popMenu.addAction(QtGui.QAction('Delete', self))
    #
    # def contextMenuEvent(self, event):
    #     # add other required actions
    #     self.popMenu.popup(QtGui.QCursor.pos())


class VehicleListView(QtWidgets.QListView):
    def __init__(self):
        super(VehicleListView, self).__init__()

class BotView(QtGui.QStandardItem):
    def __init__(self, homepath):
        super(BotView, self).__init__()
        self.setText('bot0')
        self.homepath = homepath
        self.bot0Icon = QtGui.QIcon(homepath+'/resource/images/icons/c_robot64_0.png')
        self.bot0.setIcon(self.bot0Icon)
        self.popMenu = QtWidgets.QMenu(self)
        self.popMenu.addAction(QtGui.QAction('Edit', self))
        self.popMenu.addAction(QtGui.QAction('Clone', self))
        self.popMenu.addSeparator()
        self.popMenu.addAction(QtGui.QAction('Delete', self))

    def contextMenuEvent(self, event):
        # add other required actions
        self.popMenu.popup(QtGui.QCursor.pos())

class DragIcon(QtWidgets.QLabel):

    def install_rc_menu(self):
        # create context menu
        self.popMenu = QtWidgets.QMenu(self)
        self.popMenu.addAction(QtGui.QAction('Edit', self))
        self.popMenu.addAction(QtGui.QAction('Clone', self))
        self.popMenu.addSeparator()
        self.popMenu.addAction(QtGui.QAction('Delete', self))

    def on_context_menu(self, point):
        # show context menu
        self.popMenu.exec_(self.button.mapToGlobal(point))

    def mousePressEvent(self, event):
        self.__mousePressPos = None
        self.__mouseMovePos = None
        if event.button() == QtCore.Qt.LeftButton:
            self.__mousePressPos = event.globalPos()
            self.__mouseMovePos = event.globalPos()

        super(DragIcon, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == QtCore.Qt.LeftButton:
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
        self.popMenu.popup(QtGui.QCursor.pos())


class DragPanel(QtWidgets.QFrame):
    def __init__(self):
        super(DragPanel, self).__init__()

        self.flowLayout = FlowLayout()
        #flowLayout.addWidget(QtWidgets.QLabel("Short"))
        self.setLayout(self.flowLayout)

    def addBot(self, bot):
        self.flowLayout.addWidget(bot)


class FlowLayout(QtWidgets.QLayout):
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
        return QtCore.Qt.Orientations(QtCore.Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self.doLayout(QtCore.QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super(FlowLayout, self).setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QtCore.QSize()

        for item in self.itemList:
            size = size.expandedTo(item.minimumSize())

        size += QtCore.QSize(2 * self.contentsMargins().top(), 2 * self.contentsMargins().top())
        return size

    def doLayout(self, rect, testOnly):
        x = rect.x()
        y = rect.y()
        lineHeight = 0

        for item in self.itemList:
            # wid = item.widget()
            # spaceX = self.spacing() + wid.QStyle().layoutSpacing(QtWidgets.QSizePolicy.Label, QtWidgets.QSizePolicy.Label, QtCore.Qt.Horizontal)
            # spaceY = self.spacing() + wid.QStyle().layoutSpacing(QtWidgets.QSizePolicy.Label, QtWidgets.QSizePolicy.Label, QtCore.Qt.Vertical)

            spaceX = self.spacing() + item.wid.style().layoutSpacing(QtWidgets.QSizePolicy.Label, QtWidgets.QSizePolicy.Label, QtCore.Qt.Horizontal)
            spaceY = self.spacing() + item.wid.style().layoutSpacing(QtWidgets.QSizePolicy.Label, QtWidgets.QSizePolicy.Label, QtCore.Qt.Vertical)
            nextX = x + item.sizeHint().width() + spaceX
            if nextX - spaceX > rect.right() and lineHeight > 0:
                x = rect.x()
                y = y + lineHeight + spaceY
                nextX = x + item.sizeHint().width() + spaceX
                lineHeight = 0

            if not testOnly:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), item.sizeHint()))

            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())

        return y + lineHeight - rect.y()
