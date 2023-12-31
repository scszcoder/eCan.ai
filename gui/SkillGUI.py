import sys
import random
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene, QComboBox, QWidget, QGridLayout
from PySide6.QtCore import QPointF, Qt, QEvent, QRectF
from PySide6.QtGui import QPainterPath, QPen, QColor, QPixmap, QBrush, QPainter
from PIL import Image as pimg

# from locale import getdefaultlocale
#
# import ctypes as ct
# # from ctypes import wintypes as wt
# import time
# import json
#
# from pynput import mouse
# from pynput import keyboard
# import threading
#
# import pyautogui
# from Cloud import *
# import pyqtgraph
# from pyqtgraph import flowchart
# import BorderLayout
from WorkSkill import *
from readSkill import *
from gui.skfc.skfc_widget import SkFCWidget
from gui.skcode.codeeditor.pythoneditor import PMGPythonEditor
from config.app_info import app_info


INSTALLED_PATH = ""
USER_DIR = ""
OS_DIR = ""
PAGE_DIR = ""

# skill parameters:
# skid	int(11)	NO	PRI	NULL	auto_increment
# owner	varchar(50)	YES		NULL
# platform	varchar(50)	YES		NULL
# app	varchar(50)	YES		NULL
# site	varchar(50)	YES		NULL
# name	varchar(30)	YES		NULL
# path	varchar(80)	YES		NULL
# runtime	int(11)	YES		NULL
# price_model	varchar(50)	YES		NULL
# price	int(11)	YES		NULL


class SkillListView(QtWidgets.QListView):
    def __init__(self, parent):
        super(SkillListView, self).__init__()
        self.selected_row = None
        self.parent = parent

    def mousePressEvent(self, e):
        if e.type() == QtCore.QEvent.MouseButtonPress:
            if e.button() == QtCore.Qt.LeftButton:
                print("row:", self.indexAt(e.pos()).row())
                self.selected_row = self.indexAt(e.pos()).row()
                self.parent.updateSelectedRole(self.selected_row)


class AnchorListView(QtWidgets.QListView):
    def __init__(self):
        super(AnchorListView, self).__init__()


class BSQGraphicsRectItem(QtWidgets.QGraphicsRectItem):

    handleTopLeft = 1
    handleTopMiddle = 2
    handleTopRight = 3
    handleMiddleLeft = 4
    handleMiddleRight = 5
    handleBottomLeft = 6
    handleBottomMiddle = 7
    handleBottomRight = 8

    handleSize = +6.0
    handleSpace = -3.0

    handleCursors = {
        handleTopLeft: Qt.SizeFDiagCursor,
        handleTopMiddle: Qt.SizeVerCursor,
        handleTopRight: Qt.SizeBDiagCursor,
        handleMiddleLeft: Qt.SizeHorCursor,
        handleMiddleRight: Qt.SizeHorCursor,
        handleBottomLeft: Qt.SizeBDiagCursor,
        handleBottomMiddle: Qt.SizeVerCursor,
        handleBottomRight: Qt.SizeFDiagCursor,
    }

    def __init__(self, rect, pv, rect_type="udbb"):
        """
        Initialize the shape.
        """
        super().__init__(rect)
        self.parentView = pv
        self.rect_type = rect_type
        self.handles = {}
        self.handleSelected = None
        self.mousePressPos = None
        self.mousePressRect = None
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.ItemIsFocusable, True)
        self.updateHandlesPos()
        self.mode = "quiet"

    def handleAt(self, point):
        """
        Returns the resize handle below the given point.
        """
        for k, v, in self.handles.items():
            if v.contains(point):
                return k
        return None

    def hoverMoveEvent(self, moveEvent):
        """
        Executed when the mouse moves over the shape (NOT PRESSED).
        """
        # print("hover move", moveEvent.pos())
        if self.isSelected():
            handle = self.handleAt(moveEvent.pos())
            #print("hover selected....", handle)
            cursor = Qt.ArrowCursor if handle is None else self.handleCursors[handle]
            self.setCursor(cursor)
            #self.setCursor(QtCore.Qt.ClosedHandCursor)
        super(BSQGraphicsRectItem, self).hoverMoveEvent(moveEvent)

    def hoverLeaveEvent(self, moveEvent):
        """
        Executed when the mouse leaves the shape (NOT PRESSED).
        """
        # print("hover left")
        self.setCursor(Qt.ArrowCursor)
        super(BSQGraphicsRectItem, self).hoverLeaveEvent(moveEvent)

    def mousePressEvent(self, mouseEvent):
        """
        Executed when the mouse is pressed on the item.
        """
        self.updateHandlesPos()
        orig_position = self.scenePos()
        print("press orginal: ", orig_position)
        #print("rect pressed....", self.parentView.drawStartPos)
        # self.handleSelected = self.handleAt(self.parentView.drawStartPos)
        print("mouseEvent.pos()", mouseEvent.pos())
        self.pressLocalPos = mouseEvent.pos()
        self.handleSelected = self.handleAt(mouseEvent.pos())
        print("parentView.drawStartPos", self.parentView.drawStartPos)
        self.handleSelected = self.handleAt(mouseEvent.pos())
        print("handle @ press ...", self.handleSelected)
        print("rect @ press ...", self.rect())
        print("all handles:", self.handles)
        currentMousePos = self.parentView.drawStartPos
        currentMousePos.setX(currentMousePos.x() - orig_position.x())
        currentMousePos.setY(currentMousePos.y() - orig_position.y())
        self.handleSelected = self.handleAt(currentMousePos)

        print("currentMousePos ...", currentMousePos)
        #self.handleSelected = self.handleAt(self.parentView.drawStartPos)
        print("handle @ press ...", self.handleSelected)
        if self.handleSelected:
            print("rect resizing...")
            self.mode = "resizing"
            self.parentView.set_mode(self.mode)
            #self.mousePressPos = mouseEvent.pos()
            self.mousePressPos = self.parentView.drawStartPos
            self.mousePressRect = self.boundingRect()
            # print("mousePressRect: ", self.mousePressRect)
        # super().mousePressEvent(mouseEvent)
        else:
            print("Moving.....")
            if self.contains(currentMousePos):
                self.mode = "moving"
                # self.mousePressPos = mouseEvent.pos()
                self.mousePressPos = self.parentView.drawStartPos
                self.mousePressRect = self.boundingRect()
            else:
                self.mode = "selecting"

        self.parentView.set_mode(self.mode)
        print("rect pressed....", self.mousePressPos, " rect: ", self.rect())

    def mouseReleaseEvent(self, mouseEvent):
        """
        Executed when the mouse is released from the item.
        """
        print("rect released....", mouseEvent.pos())
        self.releaseLocalPos = mouseEvent.pos()
        #super().mouseReleaseEvent(mouseEvent)

        #self.mouseReleasePos = mouseEvent.pos()
        self.mouseReleasePos = self.parentView.drawEndPos
        self.mouseReleaseRect = self.boundingRect()

        orig_position = self.scenePos()
        print("orig_position: ", orig_position, ":::", self.pos())
        print("press_position: ", self.mousePressPos)
        print("release_position: ", self.mouseReleasePos)

        if self.mode == "moving":
            print("move releasing...")
            updated_cursor_x = self.releaseLocalPos.x() - self.pressLocalPos.x() + orig_position.x()
            updated_cursor_y = self.releaseLocalPos.y() - self.pressLocalPos.y() + orig_position.y()
            self.setPos(QPointF(updated_cursor_x, updated_cursor_y))

            self.handleSelected = None
            self.mousePressPos = None
            self.mousePressRect = None
            self.update()
            self.updateHandlesPos()
            print("rect @ release ...", self.rect(), "pos:", self.pos())
        elif self.mode == "resizing":
            print("resize releasing...")
            self.interactiveResize(self.mouseReleasePos)

        self.mode = "quiet"
        self.parentView.set_mode(self.mode)

    def boundingRect(self):
        """
        Returns the bounding rect of the shape (including the resize handles).
        """
        o = self.handleSize + self.handleSpace
        return self.rect().adjusted(-o, -o, o, o)

    def updateHandlesPos(self):
        """
        Update current resize handles according to the shape size and position.
        """
        s = self.handleSize
        b = self.boundingRect()
        self.handles[self.handleTopLeft] = QRectF(b.left(), b.top(), s, s)
        self.handles[self.handleTopMiddle] = QRectF(b.center().x() - s / 2, b.top(), s, s)
        self.handles[self.handleTopRight] = QRectF(b.right() - s, b.top(), s, s)
        self.handles[self.handleMiddleLeft] = QRectF(b.left(), b.center().y() - s / 2, s, s)
        self.handles[self.handleMiddleRight] = QRectF(b.right() - s, b.center().y() - s / 2, s, s)
        self.handles[self.handleBottomLeft] = QRectF(b.left(), b.bottom() - s, s, s)
        self.handles[self.handleBottomMiddle] = QRectF(b.center().x() - s / 2, b.bottom() - s, s, s)
        self.handles[self.handleBottomRight] = QRectF(b.right() - s, b.bottom() - s, s, s)

    def interactiveResize(self, mousePos):
        """
        Perform shape interactive resize.
        """
        offset = self.handleSize + self.handleSpace
        #print("offset is ", offset)
        boundingRect = self.boundingRect()
        rect = self.rect()
        #print("bounding rect...", boundingRect, "self rect...", rect)
        diff = QPointF(0, 0)

        self.prepareGeometryChange()
        #print("resize handle selected:", self.handleSelected)
        if self.handleSelected == self.handleTopLeft:

            fromX = self.mousePressRect.left()
            fromY = self.mousePressRect.top()
            toX = fromX + mousePos.x() - self.mousePressPos.x()
            toY = fromY + mousePos.y() - self.mousePressPos.y()
            diff.setX(toX - fromX)
            diff.setY(toY - fromY)
            boundingRect.setLeft(toX)
            boundingRect.setTop(toY)
            rect.setLeft(boundingRect.left() + offset)
            rect.setTop(boundingRect.top() + offset)
            #print("rect TL:", rect)
            self.setRect(rect)

        elif self.handleSelected == self.handleTopMiddle:

            fromY = self.mousePressRect.top()
            toY = fromY + mousePos.y() - self.mousePressPos.y()
            diff.setY(toY - fromY)
            boundingRect.setTop(toY)
            rect.setTop(boundingRect.top() + offset)
            #print("rect TM:", rect)
            self.setRect(rect)

        elif self.handleSelected == self.handleTopRight:

            fromX = self.mousePressRect.right()
            fromY = self.mousePressRect.top()
            toX = fromX + mousePos.x() - self.mousePressPos.x()
            toY = fromY + mousePos.y() - self.mousePressPos.y()
            diff.setX(toX - fromX)
            diff.setY(toY - fromY)
            boundingRect.setRight(toX)
            boundingRect.setTop(toY)
            rect.setRight(boundingRect.right() - offset)
            rect.setTop(boundingRect.top() + offset)
            #print("rect TR:", rect)
            self.setRect(rect)

        elif self.handleSelected == self.handleMiddleLeft:

            fromX = self.mousePressRect.left()
            toX = fromX + mousePos.x() - self.mousePressPos.x()
            diff.setX(toX - fromX)
            boundingRect.setLeft(toX)
            rect.setLeft(boundingRect.left() + offset)
            #print("rect ML:", rect)
            self.setRect(rect)

        elif self.handleSelected == self.handleMiddleRight:
            fromX = self.mousePressRect.right()
            toX = fromX + mousePos.x() - self.mousePressPos.x()
            diff.setX(toX - fromX)
            boundingRect.setRight(toX)
            rect.setRight(boundingRect.right() - offset)
            #print("rect MR:", rect)
            self.setRect(rect)

        elif self.handleSelected == self.handleBottomLeft:

            fromX = self.mousePressRect.left()
            fromY = self.mousePressRect.bottom()
            toX = fromX + mousePos.x() - self.mousePressPos.x()
            toY = fromY + mousePos.y() - self.mousePressPos.y()
            diff.setX(toX - fromX)
            diff.setY(toY - fromY)
            boundingRect.setLeft(toX)
            boundingRect.setBottom(toY)
            rect.setLeft(boundingRect.left() + offset)
            rect.setBottom(boundingRect.bottom() - offset)
            #print("rect BL:", rect)
            self.setRect(rect)

        elif self.handleSelected == self.handleBottomMiddle:

            fromY = self.mousePressRect.bottom()
            # print("fromY:", fromY, "mouse y: ", mousePos.y(), "mouse press y: ", self.mousePressPos.y(), "toY", toY)
            toY = fromY + mousePos.y() - self.mousePressPos.y()
            diff.setY(toY - fromY)
            boundingRect.setBottom(toY)
            rect.setBottom(boundingRect.bottom() - offset)
            # print("fromY:", fromY, "mouse y: ", mousePos.y(), "mouse press y: ", self.mousePressPos.y(), "toY", toY)
            #print("rect BM:", rect)
            self.setRect(rect)

        elif self.handleSelected == self.handleBottomRight:

            fromX = self.mousePressRect.right()
            fromY = self.mousePressRect.bottom()
            toX = fromX + mousePos.x() - self.mousePressPos.x()
            toY = fromY + mousePos.y() - self.mousePressPos.y()
            diff.setX(toX - fromX)
            diff.setY(toY - fromY)
            boundingRect.setRight(toX)
            boundingRect.setBottom(toY)
            rect.setRight(boundingRect.right() - offset)
            rect.setBottom(boundingRect.bottom() - offset)
            #print("rect BR:", rect)
            self.setRect(rect)

        self.updateHandlesPos()

    def shape(self):
        """
        Returns the shape of this item as a QPainterPath in local coordinates.
        """
        path = QPainterPath()
        path.addRect(self.rect())
        if self.isSelected():
            for shape in self.handles.values():
                path.addEllipse(shape)
        return path

    def paint(self, painter, option, widget=None):
        """
        Paint the node in the graphic view.
        """
        #painter.setBrush(QBrush(QColor(255, 0, 0, 100)))
        if self.rect_type == "udbb" and not self.isSelected():
            painter.setPen(QPen(Qt.darkRed, 1.0, Qt.SolidLine))
        elif self.rect_type == "udbb" and self.isSelected():
            painter.setPen(QPen(Qt.red, 2.0, Qt.SolidLine))
        elif self.rect_type == "txtbb" and not self.isSelected():
            painter.setPen(QPen(Qt.green, 1.0, Qt.SolidLine))
        elif self.rect_type == "txtbb" and self.isSelected():
            painter.setPen(QPen(Qt.green, 2.0, Qt.SolidLine))
        elif self.rect_type == "imgbb" and not self.isSelected():
            painter.setPen(QPen(QColor(250, 140, 0, 255), 1.0, Qt.SolidLine))
        elif self.rect_type == "imgbb" and self.isSelected():
            painter.setPen(QPen(Qt.yellow, 2.0, Qt.SolidLine))
        painter.drawRect(self.rect())

        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor(255, 0, 0, 255)))
        painter.setPen(QPen(QColor(0, 0, 0, 255), 1.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        if self.isSelected():
            for handle, rect in self.handles.items():
                if self.handleSelected is None or handle == self.handleSelected:
                    painter.drawEllipse(rect)


class BSQGraphicsScene(QGraphicsScene):
    def __init__(self, parent):
        super(BSQGraphicsScene, self).__init__()
        self.setParent(parent)
        self.current_items = []
        self.mode = "quiet"

    def set_mode(self, inmode):
        self.mode = inmode
        self.parent().set_pb_mode = inmode


    def mousePressEvent(self, event):
        selected = self.selectedItems()
        if len(selected) == 0:
            print("scene press nothing selected....")
            # rect = BSQGraphicsRectItem(QtCore.QRectF(rectPos[0], rectPos[1], rectPos[2], rectPos[3]))
            # rect.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable)
            # rect.setPen(self.parentWin.udBoxPen)
            # self.parentWin.pbscene.addItem(rect)
            # self.update()
            # self.rects.append(rect)
        else:
            # redraw selected item with selected pen.
            print("selected scene press")
            for ri in selected:
                print("pos:", self.parent().pbview.drawStartPos)
                #ri.mousePressEvent(event.pos())
                ri.mousePressEvent(event)

        if event.buttons() == QtCore.Qt.RightButton:
            pos = self.parent().pbview.mapToScene(event.pos())
            self.current_items = self.find_rect_by_pos(pos)

    def mouseReleaseEvent(self, event):
        selected = self.selectedItems()
        if len(selected) == 0:
            print("scene release nothing selected....")
            # rect = BSQGraphicsRectItem(QtCore.QRectF(rectPos[0], rectPos[1], rectPos[2], rectPos[3]))
            # rect.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable)
            # rect.setPen(self.parentWin.udBoxPen)
            # self.parentWin.pbscene.addItem(rect)
            # self.update()
            # self.rects.append(rect)
        else:
            # redraw selected item with selected pen.
            print("scene release")
            for ri in selected:
                ri.mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        # print("scene moving....")
        selected = self.selectedItems()
        if len(selected) > 0:
            # redraw selected item with selected pen.
            if event.buttons() == QtCore.Qt.LeftButton:
                for ri in selected:
                    #print("resizing.....", event.scenePos(), "   ", self.parent().pbview.mapToScene(event.scenePos().toPoint()))
                    #ri.interactiveResize(self.parent().pbview.mapToScene(event.pos().toPoint()))
                    #ri.interactiveResize(self.parent().pbview.mapToScene(event.scenePos().toPoint()))
                    ri.interactiveResize(event.scenePos().toPoint())
        super(BSQGraphicsScene,  self).mouseMoveEvent(event)


    def find_rect_by_pos(self, pos):
        result = []
        item = self.itemAt(pos, QtGui.QTransform())

        result.append(item)
        return result

    def mouseDoubleClickEvent(self, event):
        print("mouse double clicked.....")


# BS stands for Bot Skill
class BSQGraphicsView(QtWidgets.QGraphicsView):
    def __init__(self, inscene, parent):
        super(BSQGraphicsView, self).__init__(inscene, parent)
        self.parentWin = parent
        self.setScene(inscene)
        self.mode = "quiet"

    def set_mode(self, inmode):
        self.mode = inmode

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            print("rubber band: ", self.rubberBandRect())
            self.drawEndPos = self.mapToScene(event.pos())
            print("mouse released at: ", self.drawEndPos, "in mode: ", self.mode)
            rectPos = self.parentWin.formRectPos(self.drawStartPos, self.drawEndPos)
            print("rect area: ", rectPos)
            selpath = QPainterPath()
            # selpath.addRect(self.rubberBandRect())
            if self.mode == "quiet":
                selpath.addRect(rectPos[0], rectPos[1], rectPos[2], rectPos[3])
                self.scene().setSelectionArea(selpath, Qt.ReplaceSelection, Qt.ContainsItemShape, QtGui.QTransform(1, 0, 0, 0, 1, 0, 0, 0, 1))

            selected = self.scene().selectedItems()
            print("# selected: ", selected)
            if len(selected) == 0:
                print("at release, nothing selected....")
                rect = BSQGraphicsRectItem(QtCore.QRectF(rectPos[0], rectPos[1], rectPos[2], rectPos[3]), self)
                rect.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable)
                rect.setPen(self.parentWin.udBoxPen)
                self.parentWin.pbscene.addItem(rect)
                self.update()
                # self.rects.append(rect)
            else:
                # redraw selected item with selected pen.
                # for ri in selected:
                #     ri.setPen((self.parentWin.txtBoxSelPen))
                self.scene().mouseReleaseEvent(event)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            print("view press event", event.pos(), "::", event.screenPos(), ":::", event.scenePosition())
            self.drawStartPos = self.mapToScene(event.pos())
            self.drawStartScenePos = self.mapToScene(event.scenePosition().toPoint())
            #self.drawStartPos = self.mapToScene(event.scenePosition().toPoint())
            selected = self.scene().selectedItems()
            print("# selected: ", selected)
        elif event.button() == QtCore.Qt.RightButton:
            self.rightClickPos = self.mapToScene(event.pos())

        selected = self.scene().selectedItems()

        self.scene().mousePressEvent(event)
        #for ri in selected:
        #    ri.mousePressEvent(event)


OFFSET_UNITS = ['Pixel', 'Letter Height', 'Image Height', 'Full Height', 'Letter Width', 'Image Width', 'Full Width']
OFFSET_TYPES = ['Absolute', 'Signed', 'Absolute Percent', 'Signed Percent']
ACTION_ITEMS = ['App Page Open', 'Browse', 'Create Data', 'Mouse Action', 'Keyboard Action', 'Load Data', 'Save Data',
                'Conditional Step', 'Jump Step', 'Run Routine', 'Set Wait', 'Halt', 'Run Routine', 'Run Extern']


class SkillGUI(QtWidgets.QMainWindow):
    def __init__(self, parent):
        super(SkillGUI, self).__init__(parent)

        self.newSkill = None
        self.home_path = app_info.app_home_path
        self.skill_path = ""
        self.parent = parent

        self.newUserInfo = None
        self.newAnchor = None

        self.currentSkill = None

        self.session = None
        self.cog = None
        self.rects = []

        self.pb_mode = "quiet"
        # ------- widgets ------------
        # self.popMenu = QtWidgets.QMenu(self)
        # self.popMenu.addAction(QtGui.QAction('Set Anchor', self))
        # self.popMenu.addAction(QtGui.QAction('Set Info', self))
        # self.popMenu.addSeparator()
        # self.popMenu.addAction(QtGui.QAction('Clear Boundbox', self))

        self.skfsel = QtWidgets.QFileDialog()
        # self.vsplitter2 = QtWidgets.QSplitter(Qt.Horizontal)

        self.step_count = 0
        self.step_names = []

        # ------ PbRun layout Start ------ #
        self.playback_start_button = QtWidgets.QPushButton(QtWidgets.QApplication.translate("QtWidgets.QPushButton", "Start Playback"))
        self.playback_next_button = QtWidgets.QPushButton(QtWidgets.QApplication.translate("QtWidgets.QPushButton", "Next"))
        self.playback_back_button = QtWidgets.QPushButton(QtWidgets.QApplication.translate("QtWidgets.QPushButton", "Back"))
        self.playback_reload_button = QtWidgets.QPushButton(QtWidgets.QApplication.translate("QtWidgets.QPushButton", "Refresh"))

        self.pbbuttonlayout = QtWidgets.QHBoxLayout()
        self.pbbuttonlayout.addWidget(self.playback_start_button)
        self.pbbuttonlayout.addWidget(self.playback_next_button)
        self.pbbuttonlayout.addWidget(self.playback_back_button)
        self.pbbuttonlayout.addWidget(self.playback_reload_button)

        self.playback_start_button.clicked.connect(self.start_train)
        self.playback_next_button.clicked.connect(self.train_next_step)
        self.playback_back_button.clicked.connect(self.train_prev_step)
        self.playback_reload_button.clicked.connect(self.re_train_step)
        # self.pbmainwin = QtWidgets.QScrollArea()
        # self.pbmainwin.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        # self.pbmainwin.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)

        self.pic = QtWidgets.QGraphicsPixmapItem()
        file_name = self.home_path + "resource/skills/temp/step1.png"
        self.load_image_file(file_name)

        img_size = self.pic.pixmap().size()
        print("image size: " + str(img_size.width()) + ", " + str(img_size.height()))

        # self.pbscene = QGraphicsScene()
        self.pbscene = BSQGraphicsScene(self)
        self.pbscene.setSceneRect(0, 0, img_size.width(), img_size.height())
        self.pbscene.addItem(self.pic)
        self.pbview = BSQGraphicsView(self.pbscene, self)
        # self.pbview = QGraphicsView(self.pbscene)
        #self.pbview.setRubberBandSelectionMode(Qt.ContainsItemBoundingRect)
        #self.pbview.setDragMode(QGraphicsView.RubberBandDrag)
        self.pbview.setContextMenuPolicy(Qt.DefaultContextMenu)
        self.pbview.installEventFilter(self)

        self.pbrunlayout = QtWidgets.QVBoxLayout()
        self.pbrunlayout.addLayout(self.pbbuttonlayout)
        self.pbrunlayout.addWidget(self.pbview)
        self.pbrunWidget = QtWidgets.QWidget()
        self.pbrunWidget.setLayout(self.pbrunlayout)

        self.brush = QBrush()

        self.txtboxPenColor = Qt.darkRed
        self.txtboxPenWidth = 2
        self.txtboxSelPenColor = Qt.red
        self.txtboxSelPenWidth = 3
        self.imgboxPenColor = Qt.darkGreen
        self.imgboxPenWidth = 2
        self.imgboxSelPenColor = Qt.green
        self.imgboxSelPenWidth = 3
        self.udBoxPenColor = Qt.darkYellow
        self.udBoxPenWidth = 2
        self.udBoxSelPenColor = Qt.yellow
        self.udBoxSelPenWidth = 3

        self.txtBoxPen = QPen()
        self.txtBoxPen.setStyle(Qt.DashLine)
        self.txtBoxPen.setWidth(self.txtboxPenWidth)
        self.txtBoxPen.setBrush(self.txtboxPenColor)
        self.txtBoxPen.setCapStyle(Qt.RoundCap)
        self.txtBoxPen.setJoinStyle(Qt.RoundJoin)

        self.txtBoxSelPen = QPen()
        self.txtBoxSelPen.setStyle(Qt.DashLine)
        self.txtBoxSelPen.setWidth(self.txtboxSelPenWidth)
        self.txtBoxSelPen.setBrush(self.txtboxSelPenColor)
        self.txtBoxSelPen.setCapStyle(Qt.RoundCap)
        self.txtBoxSelPen.setJoinStyle(Qt.RoundJoin)

        self.txtBoxPen = QPen()
        self.txtBoxPen.setStyle(Qt.DashLine)
        self.txtBoxPen.setWidth(self.txtboxPenWidth)
        self.txtBoxPen.setBrush(self.txtboxPenColor)
        self.txtBoxPen.setCapStyle(Qt.RoundCap)
        self.txtBoxPen.setJoinStyle(Qt.RoundJoin)

        self.imgBoxPen = QPen()
        self.imgBoxPen.setStyle(Qt.DashLine)
        self.imgBoxPen.setWidth(self.imgboxPenWidth)
        self.imgBoxPen.setBrush(self.imgboxPenColor)
        self.imgBoxPen.setCapStyle(Qt.RoundCap)
        self.imgBoxPen.setJoinStyle(Qt.RoundJoin)

        self.imgBoxSelPen = QPen()
        self.imgBoxSelPen.setStyle(Qt.DashLine)
        self.imgBoxSelPen.setWidth(self.imgboxSelPenWidth)
        self.imgBoxSelPen.setBrush(self.imgboxSelPenColor)
        self.imgBoxSelPen.setCapStyle(Qt.RoundCap)
        self.imgBoxSelPen.setJoinStyle(Qt.RoundJoin)

        self.udBoxPen = QPen()
        self.udBoxPen.setStyle(Qt.DashLine)
        self.udBoxPen.setWidth(self.udBoxPenWidth)
        self.udBoxPen.setBrush(self.udBoxPenColor)
        self.udBoxPen.setCapStyle(Qt.RoundCap)
        self.udBoxPen.setJoinStyle(Qt.RoundJoin)

        self.udBoxSelPen = QPen()
        self.udBoxSelPen.setStyle(Qt.DashLine)
        self.udBoxSelPen.setWidth(self.udBoxSelPenWidth)
        self.udBoxSelPen.setBrush(self.udBoxSelPenColor)
        self.udBoxSelPen.setCapStyle(Qt.RoundCap)
        self.udBoxSelPen.setJoinStyle(Qt.RoundJoin)


        #rect = QtWidgets.QGraphicsRectItem(QtCore.QRectF(10, 10, 25, 25))
        rect = BSQGraphicsRectItem(QtCore.QRectF(10, 10, 25, 25), self.pbview, "txtbb")
        rect.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable)
        rect.setPen(self.txtBoxPen)
        self.pbscene.addItem(rect)
        self.rects.append(rect)

        # rect = QtWidgets.QGraphicsRectItem(QtCore.QRectF(50, 50, 25, 25))
        rect = BSQGraphicsRectItem(QtCore.QRectF(50, 50, 25, 25), self.pbview, "imgbb")
        rect.setPen(self.txtBoxPen)
        rect.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable)
        self.pbscene.addItem(rect)
        self.rects.append(rect)

        # self.pbmainwin.setWidget(self.pbview)
        # ------ PbRun layout End ------ #

        # ------ pbsk header layout Start ----- #
        self.pbskAppLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "App: "))
        self.pbskAppLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbskAppEdit = QtWidgets.QLineEdit()
        self.pbskAppEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "type in App name here"))
        self.pbskAppEdit.textChanged.connect(self.appDomainPage_changed)

        self.pbskAppExeLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "App Exe Path: "))
        self.pbskAppExeLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbskAppExeEdit = QtWidgets.QLineEdit()
        self.pbskAppExeEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "type in App Exe Full Path here"))
        self.pbskAppExeEdit.textChanged.connect(self.appDomainPage_changed)

        self.pbskDomainLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Site: "))
        self.pbskDomainLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbskDomainEdit = QtWidgets.QLineEdit()
        self.pbskDomainEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "type in Domain Site here"))
        self.pbskDomainEdit.textChanged.connect(self.appDomainPage_changed)

        self.pbskDomainURLLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Site URL: "))
        self.pbskDomainURLLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbskDomainURLEdit = QtWidgets.QLineEdit()
        self.pbskDomainURLEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "type in Site URL here"))
        self.pbskDomainURLEdit.textChanged.connect(self.appDomainPage_changed)


        self.pbskPageLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Page: "))
        self.pbskPageLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbskPageEdit = QtWidgets.QLineEdit()
        self.pbskPageEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "type in page name here"))
        self.pbskPageEdit.textChanged.connect(self.appDomainPage_changed)

        self.pbskSkillLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Skill: "))
        self.pbskSkillLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbskSkillEdit = QtWidgets.QLineEdit()
        self.pbskSkillEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "type in skill name here"))
        self.pbskSkillEdit.textChanged.connect(self.appDomainPage_changed)

        self.pbActionLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Action: "))
        self.pbActionLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbActionSel = QtWidgets.QComboBox()
        self.add_items_of_combobox(self.pbActionSel, ACTION_ITEMS)
        self.pbActionSel.currentTextChanged.connect(self.pbActionSel_changed)

        pbsk_headers_widgets = [
            (self.pbskAppLabel, self.pbskAppEdit),
            (self.pbskAppExeLabel, self.pbskAppExeEdit),
            (self.pbskDomainLabel, self.pbskDomainEdit),
            (self.pbskDomainURLLabel, self.pbskDomainURLEdit),
            (self.pbskPageLabel, self.pbskPageEdit),
            (self.pbskSkillLabel, self.pbskSkillEdit),
            (self.pbActionLabel, self.pbActionSel)
        ]
        self.pbsk_header_layout = QGridLayout()
        self.add_widgets_of_gridlayout(self.pbsk_header_layout, pbsk_headers_widgets)
        self.pbsk_header_widget = QWidget()
        self.pbsk_header_widget.setLayout(self.pbsk_header_layout)
        # ------ pbsk header layout End ----- #

        # ------ pbsk PbInfo Part Start -------- #
        self.pbInfoLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Info Type:"))
        self.pbInfoLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbInfoSel = QtWidgets.QComboBox()
        self.pbInfoSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Anchor"))
        self.pbInfoSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Useful Data"))
        self.pbInfoSel.currentTextChanged.connect(self.pbInfoSel_changed)

        self.pbRTLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref. Type: "))
        self.pbRTLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRTSel = QtWidgets.QComboBox()
        self.pbRTSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "No Ref"))
        self.pbRTSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "By Offset"))
        self.pbRTSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "By Bound Box"))
        self.pbRTSel.currentTextChanged.connect(self.pbRTSel_changed)

        self.pbNRefLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "# of Refs:"))
        self.pbNRefLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbNRefSel = QtWidgets.QComboBox()
        self.add_items_of_combobox(self.pbNRefSel, ['0', '1', '2', '3', '4'])
        self.pbNRefSel.currentTextChanged.connect(self.pbNRefSel_changed)

        self.pbATLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Anchor Type:"))
        self.pbATLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbATSel = QtWidgets.QComboBox()
        self.pbATSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Text"))
        self.pbATSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Image"))

        self.pbDTLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Data Type:"))
        self.pbDTLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbDTSel = QtWidgets.QComboBox()
        self.pbDTSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Paragraph"))
        self.pbDTSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Lines"))
        self.pbDTSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Words"))

        self.pbNLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "# of Lines:"))
        self.pbNLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbNEdit = QtWidgets.QLineEdit()
        self.pbNEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "type number of lines here"))

        self.pbInfoNameLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Name:"))
        self.pbInfoNameLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbInfoNameEdit = QtWidgets.QLineEdit()
        self.pbInfoNameEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "Ex: abc"))

        # ----------  reference 1 widgets ----------------------------
        self.pbRef1NameLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref1 Name:"))
        self.pbRef1NameLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef1NameEdit = QtWidgets.QLineEdit()
        self.pbRef1NameEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "Ex: abc"))

        self.pbRef1XOffsetDirLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref1 X Offset Dir:"))
        self.pbRef1XOffsetDirLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef1XOffsetDirSel = QtWidgets.QComboBox()
        self.pbRef1XOffsetDirSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Within"))
        self.pbRef1XOffsetDirSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Beyond"))

        self.pbRef1XOffsetTypeLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref1 X Offset Type:"))
        self.pbRef1XOffsetTypeLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef1XOffsetTypeSel = QtWidgets.QComboBox()
        self.add_items_of_combobox(self.pbRef1XOffsetTypeSel, OFFSET_TYPES)

        self.pbRef1XOffsetValLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref1 X Offset Value: "))
        self.pbRef1XOffsetValLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef1XOffsetValEdit = QtWidgets.QLineEdit()
        self.pbRef1XOffsetValEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "Ex: 1"))

        self.pbRef1XOffsetUnitLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref1 X Offset Unit: "))
        self.pbRef1XOffsetUnitLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef1XOffsetUnitSel = QtWidgets.QComboBox()
        self.add_items_of_combobox(self.pbRef1XOffsetUnitSel, OFFSET_UNITS)

        self.pbRef1YOffsetDirLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref1 Y Dir: "))
        self.pbRef1YOffsetDirLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef1YOffsetDirSel = QtWidgets.QComboBox()
        self.pbRef1YOffsetDirSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Within"))
        self.pbRef1YOffsetDirSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Beyond"))

        self.pbRef1YOffsetTypeLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref1 Y Offset Type: "))
        self.pbRef1YOffsetTypeLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef1YOffsetTypeSel = QtWidgets.QComboBox()
        self.add_items_of_combobox(self.pbRef1YOffsetTypeSel, OFFSET_TYPES)

        self.pbRef1YOffsetValLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref1 Y Offset Value: "))
        self.pbRef1YOffsetValLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef1YOffsetValEdit = QtWidgets.QLineEdit()
        self.pbRef1YOffsetValEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "Ex: 1"))

        self.pbRef1YOffsetUnitLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref1 Y Offset Unit: "))
        self.pbRef1YOffsetUnitLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef1YOffsetUnitSel = QtWidgets.QComboBox()
        self.add_items_of_combobox(self.pbRef1YOffsetUnitSel, OFFSET_UNITS)

        #  ----------  reference 2 widgets ----------------------------
        self.pbRef2NameLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref2 Name: "))
        self.pbRef2NameLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef2NameEdit = QtWidgets.QLineEdit()
        self.pbRef2NameEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "Ex: abc"))

        self.pbRef2XOffsetDirLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref2 X Offset Dir: "))
        self.pbRef2XOffsetDirLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef2XOffsetDirSel = QtWidgets.QComboBox()
        self.pbRef2XOffsetDirSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Within"))
        self.pbRef2XOffsetDirSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Beyond"))

        self.pbRef2XOffsetTypeLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref2 X Offset Type: "))
        self.pbRef2XOffsetTypeLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef2XOffsetTypeSel = QtWidgets.QComboBox()
        self.add_items_of_combobox(self.pbRef2XOffsetTypeSel, OFFSET_TYPES)

        self.pbRef2XOffsetValLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref2 X Offset Value: "))
        self.pbRef2XOffsetValLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef2XOffsetValEdit = QtWidgets.QLineEdit()
        self.pbRef2XOffsetValEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "Ex: 1"))

        self.pbRef2XOffsetUnitLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref2 X Offset Unit: "))
        self.pbRef2XOffsetUnitLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef2XOffsetUnitSel = QtWidgets.QComboBox()
        self.add_items_of_combobox(self.pbRef2XOffsetUnitSel, OFFSET_UNITS)

        self.pbRef2YOffsetDirLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref2 Y Dir: "))
        self.pbRef2YOffsetDirLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef2YOffsetDirSel = QtWidgets.QComboBox()
        self.pbRef2YOffsetDirSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Within"))
        self.pbRef2YOffsetDirSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Beyond"))

        self.pbRef2YOffsetTypeLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref2 Y Offset Type: "))
        self.pbRef2YOffsetTypeLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef2YOffsetTypeSel = QtWidgets.QComboBox()
        self.add_items_of_combobox(self.pbRef2YOffsetTypeSel, OFFSET_TYPES)

        self.pbRef2YOffsetValLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref2 Y Offset Value: "))
        self.pbRef2YOffsetValLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef2YOffsetValEdit = QtWidgets.QLineEdit()
        self.pbRef2YOffsetValEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "Ex: 1"))

        self.pbRef2YOffsetUnitLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref2 Y Offset Unit: "))
        self.pbRef2YOffsetUnitLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef2YOffsetUnitSel = QtWidgets.QComboBox()
        self.add_items_of_combobox(self.pbRef2YOffsetUnitSel, OFFSET_UNITS)

        #  ----------  reference 3 widgets ----------------------------
        self.pbRef3NameLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref3 Name: "))
        self.pbRef3NameLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef3NameEdit = QtWidgets.QLineEdit()
        self.pbRef3NameEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "Ex: abc"))

        self.pbRef3XOffsetDirLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref3 X Offset Dir: "))
        self.pbRef3XOffsetDirLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef3XOffsetDirSel = QtWidgets.QComboBox()
        self.pbRef3XOffsetDirSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Within"))
        self.pbRef3XOffsetDirSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Beyond"))

        self.pbRef3XOffsetTypeLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref3 X Offset Type: "))
        self.pbRef3XOffsetTypeLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef3XOffsetTypeSel = QtWidgets.QComboBox()
        self.add_items_of_combobox(self.pbRef3XOffsetTypeSel, OFFSET_TYPES)

        self.pbRef3XOffsetValLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref3 X Offset Value: "))
        self.pbRef3XOffsetValLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef3XOffsetValEdit = QtWidgets.QLineEdit()
        self.pbRef3XOffsetValEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "Ex: 1"))

        self.pbRef3XOffsetUnitLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref3 X Offset Unit: "))
        self.pbRef3XOffsetUnitLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef3XOffsetUnitSel = QtWidgets.QComboBox()
        self.add_items_of_combobox(self.pbRef3XOffsetUnitSel, OFFSET_UNITS)

        self.pbRef3YOffsetDirLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref3 Y Dir: "))
        self.pbRef3YOffsetDirLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef3YOffsetDirSel = QtWidgets.QComboBox()
        self.pbRef3YOffsetDirSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Within"))
        self.pbRef3YOffsetDirSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Beyond"))

        self.pbRef3YOffsetTypeLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref3 Y Offset Type: "))
        self.pbRef3YOffsetTypeLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef3YOffsetTypeSel = QtWidgets.QComboBox()
        self.add_items_of_combobox(self.pbRef3YOffsetTypeSel, OFFSET_TYPES)

        self.pbRef3YOffsetValLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref3 Y Offset Value: "))
        self.pbRef3YOffsetValLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef3YOffsetValEdit = QtWidgets.QLineEdit()
        self.pbRef3YOffsetValEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "Ex: 1"))

        self.pbRef3YOffsetUnitLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref3 Y Offset Unit: "))
        self.pbRef3YOffsetUnitLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef3YOffsetUnitSel = QtWidgets.QComboBox()
        self.add_items_of_combobox(self.pbRef3YOffsetUnitSel, OFFSET_UNITS)

        #  ----------  reference 4 widgets ----------------------------
        self.pbRef4NameLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref4 Name: "))
        self.pbRef4NameLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef4NameEdit = QtWidgets.QLineEdit()
        self.pbRef4NameEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "Ex: abc"))

        self.pbRef4XOffsetDirLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref4 X Offset Dir: "))
        self.pbRef4XOffsetDirLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef4XOffsetDirSel = QtWidgets.QComboBox()
        self.pbRef4XOffsetDirSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Within"))
        self.pbRef4XOffsetDirSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Beyond"))

        self.pbRef4XOffsetTypeLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref4 X Offset Type: "))
        self.pbRef4XOffsetTypeLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef4XOffsetTypeSel = QtWidgets.QComboBox()
        self.add_items_of_combobox(self.pbRef4XOffsetTypeSel, OFFSET_TYPES)

        self.pbRef4XOffsetValLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref4 X Offset Value: "))
        self.pbRef4XOffsetValLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef4XOffsetValEdit = QtWidgets.QLineEdit()
        self.pbRef4XOffsetValEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "Ex: 1"))

        self.pbRef4XOffsetUnitLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref4 X Offset Unit: "))
        self.pbRef4XOffsetUnitLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef4XOffsetUnitSel = QtWidgets.QComboBox()
        self.add_items_of_combobox(self.pbRef4XOffsetUnitSel, OFFSET_UNITS)

        self.pbRef4YOffsetDirLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref4 Y Dir: "))
        self.pbRef4YOffsetDirLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef4YOffsetDirSel = QtWidgets.QComboBox()
        self.pbRef4YOffsetDirSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Within"))
        self.pbRef4YOffsetDirSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Beyond"))

        self.pbRef4YOffsetTypeLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref4 Y Offset Type: "))
        self.pbRef4YOffsetTypeLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef4YOffsetTypeSel = QtWidgets.QComboBox()
        self.add_items_of_combobox(self.pbRef4YOffsetTypeSel, OFFSET_TYPES)

        self.pbRef4YOffsetValLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref4 Y Offset Value: "))
        self.pbRef4YOffsetValLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef4YOffsetValEdit = QtWidgets.QLineEdit()
        self.pbRef4YOffsetValEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "Ex: 1"))

        self.pbRef4YOffsetUnitLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Ref4 Y Offset Unit: "))
        self.pbRef4YOffsetUnitLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRef4YOffsetUnitSel = QtWidgets.QComboBox()
        self.add_items_of_combobox(self.pbRef4YOffsetUnitSel, OFFSET_UNITS)

        # end of reference widgets.
        pbinfo_widgets = [
            (self.pbInfoNameLabel, self.pbInfoNameEdit),                # L0
            (self.pbInfoLabel, self.pbInfoSel),                         # L1
            (self.pbATLabel, self.pbATSel),                             # L2A
            (self.pbRTLabel, self.pbRTSel),                             # L2
            (self.pbNRefLabel, self.pbNRefSel),                         # L2B
            (self.pbDTLabel, self.pbDTSel),                             # L3
            (self.pbNLabel, self.pbNEdit),                              # L4
            (self.pbRef1NameLabel, self.pbRef1NameEdit),                # ref1 L5
            (self.pbRef1XOffsetDirLabel, self.pbRef1XOffsetDirSel),     # L6
            (self.pbRef1XOffsetTypeLabel, self.pbRef1XOffsetTypeSel),   # L6A
            (self.pbRef1XOffsetValLabel, self.pbRef1XOffsetValEdit),    # L6B
            (self.pbRef1XOffsetUnitLabel, self.pbRef1XOffsetUnitSel),   # L6C
            (self.pbRef1YOffsetDirLabel, self.pbRef1YOffsetDirSel),     # L7
            (self.pbRef1YOffsetTypeLabel, self.pbRef1YOffsetTypeSel),   # L7A
            (self.pbRef1YOffsetValLabel, self.pbRef1YOffsetValEdit),    # L7B
            (self.pbRef1YOffsetUnitLabel, self.pbRef1YOffsetUnitSel),   # L7C
            (self.pbRef2NameLabel, self.pbRef2NameEdit),                # ref2 L8
            (self.pbRef2XOffsetDirLabel, self.pbRef2XOffsetDirSel),     # L9
            (self.pbRef2XOffsetTypeLabel, self.pbRef2XOffsetTypeSel),   # L9A
            (self.pbRef2XOffsetValLabel, self.pbRef2XOffsetValEdit),    # L9B
            (self.pbRef2XOffsetUnitLabel, self.pbRef2XOffsetUnitSel),   # L9C
            (self.pbRef2YOffsetDirLabel, self.pbRef2YOffsetDirSel),     # L10
            (self.pbRef2YOffsetTypeLabel, self.pbRef2YOffsetTypeSel),   # L10A
            (self.pbRef2YOffsetValLabel, self.pbRef2YOffsetValEdit),    # L10B
            (self.pbRef2YOffsetUnitLabel, self.pbRef2YOffsetUnitSel),   # L10C
            (self.pbRef3NameLabel, self.pbRef3NameEdit),                # ref3 L11
            (self.pbRef3XOffsetDirLabel, self.pbRef3XOffsetDirSel),     # L12
            (self.pbRef3XOffsetTypeLabel, self.pbRef3XOffsetTypeSel),   # L12A
            (self.pbRef3XOffsetValLabel, self.pbRef3XOffsetValEdit),    # L12B
            (self.pbRef3XOffsetUnitLabel, self.pbRef3XOffsetUnitSel),   # L12C
            (self.pbRef3YOffsetDirLabel, self.pbRef3YOffsetDirSel),     # L13
            (self.pbRef3YOffsetTypeLabel, self.pbRef3YOffsetTypeSel),   # L13A
            (self.pbRef3YOffsetValLabel, self.pbRef3YOffsetValEdit),    # L13B
            (self.pbRef3YOffsetUnitLabel, self.pbRef3YOffsetUnitSel),   # L13C
            (self.pbRef4NameLabel, self.pbRef4NameEdit),                # ref4 L14
            (self.pbRef4XOffsetDirLabel, self.pbRef4XOffsetDirSel),     # L15
            (self.pbRef4XOffsetTypeLabel, self.pbRef4XOffsetTypeSel),   # L15A
            (self.pbRef4XOffsetValLabel, self.pbRef4XOffsetValEdit),    # L15B
            (self.pbRef4XOffsetUnitLabel, self.pbRef4XOffsetUnitSel),   # L15C
            (self.pbRef4YOffsetDirLabel, self.pbRef4YOffsetDirSel),     # L16
            (self.pbRef4YOffsetTypeLabel, self.pbRef4YOffsetTypeSel),   # L16A
            (self.pbRef4YOffsetValLabel, self.pbRef4YOffsetValEdit),    # L16B
            (self.pbRef4YOffsetUnitLabel, self.pbRef4YOffsetUnitSel)    # L16C
            ]
        self.pbInfoLayout = QtWidgets.QGridLayout()
        self.add_widgets_of_gridlayout(self.pbInfoLayout, pbinfo_widgets)
        self.pbInfoWidget = QWidget()
        self.pbInfoWidget.setLayout(self.pbInfoLayout)

        self.pbInfoArea = QtWidgets.QScrollArea()
        self.pbInfoArea.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.pbInfoArea.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.pbInfoArea.setWidgetResizable(True)
        self.pbInfoArea.setWidget(self.pbInfoWidget)
        # ------- pbsk PbInfo Part End ------- #

        # ------- pbsk PbAction Part Start ------- #
        self.pbStepNameLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Step Name: "))
        self.pbStepNameLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbStepNameEdit = QtWidgets.QLineEdit()
        self.pbStepNameEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "Ex: Step1"))

        self.pbStepNumberLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Step #: "))
        self.pbStepNumberLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbStepNumberEdit = QtWidgets.QLineEdit()
        self.pbStepNumberEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "Ex: 1"))

        self.pbStepPrevNextLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Located "))
        self.pbStepPrevNextLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbStepPrevNextSel = QtWidgets.QComboBox()
        self.pbStepPrevNextSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "After"))
        self.pbStepPrevNextSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Before"))
        self.pbStepPrevNextSel.currentTextChanged.connect(self.pbStepPrevNextSel_changed)

        self.pbStepPrevNextNameLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Prev. Step Name: "))
        self.pbStepPrevNextNameLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbStepPrevNextNameEdit = QtWidgets.QLineEdit()
        self.stepNameCompleter = QtWidgets.QCompleter(self.step_names)
        self.pbStepPrevNextNameEdit.setCompleter(self.stepNameCompleter)
        self.pbStepPrevNextNameEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "Ex: step1"))

        self.pbAppLinkLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "App Exe: "))
        self.pbAppLinkLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbAppLinkEdit = QtWidgets.QLineEdit()
        self.pbAppLinkEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "Full Path To .exe"))

        self.pbPageURLLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Page URL: "))
        self.pbPageURLLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbPageURLEdit = QtWidgets.QLineEdit()
        self.pbPageURLEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "full url"))

        self.pbDataNameLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Data Name: "))
        self.pbDataNameLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbDataNameEdit = QtWidgets.QLineEdit()
        self.pbDataNameEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "ex: abc"))

        self.pbMouseActionLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Mouse Action: "))
        self.pbMouseActionLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbMouseActionSel = QtWidgets.QComboBox()
        self.add_items_of_combobox(self.pbMouseActionSel, ['Single Click', 'Double Click', 'Right Click', 'Scroll Up', 'Scroll Down'])

        self.pbMouseActionAmountLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Scroll Amount: "))
        self.pbMouseActionAmountLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbMouseActionAmountEdit = QtWidgets.QLineEdit()
        self.pbMouseActionAmountEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "ex: 4"))

        self.pbKeyboardActionLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "String To Input: "))
        self.pbKeyboardActionLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbKeyboardActionEdit = QtWidgets.QLineEdit()
        self.pbKeyboardActionEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "ex: abc"))

        self.pbDataFileLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "File Name: "))
        self.pbDataFileLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbDataFileEdit = QtWidgets.QLineEdit()
        self.pbDataFileEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "full path to data file"))

        self.pbConditionLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Condition Expression: "))
        self.pbConditionLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbConditionEdit = QtWidgets.QLineEdit()
        self.pbConditionEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "example: a > 5"))

        self.pbConditionTrueLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "If True: "))
        self.pbConditionTrueLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbConditionTrueEdit = QtWidgets.QLineEdit()
        self.pbConditionTrueEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "step name here"))

        self.pbConditionFalseLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "If False: "))
        self.pbConditionFalseLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbConditionFalseEdit = QtWidgets.QLineEdit()
        self.pbConditionFalseEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "step name here"))

        self.pbJumpLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Jump to: "))
        self.pbJumpLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbJumpEdit = QtWidgets.QLineEdit()
        self.pbJumpEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "step name here"))

        self.pbRoutineLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Subroutine Name: "))
        self.pbRoutineLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbRoutineEdit = QtWidgets.QLineEdit()
        self.pbRoutineEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "subroutine name here"))

        self.pbExternLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "External Script: "))
        self.pbExternLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbExternEdit = QtWidgets.QLineEdit()
        self.pbExternEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "extern script name here"))

        self.pbWaittimeLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Wait Time: "))
        self.pbWaittimeLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pbWaittimeEdit = QtWidgets.QLineEdit()
        self.pbWaittimeEdit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "time in seconds."))

        pbAction_widgets = [
            (self.pbStepNameLabel, self.pbStepNameEdit),                    # L0
            (self.pbStepNumberLabel, self.pbStepNumberEdit),                # L0A
            (self.pbStepPrevNextLabel, self.pbStepPrevNextSel),             # L0B
            (self.pbStepPrevNextNameLabel, self.pbStepPrevNextNameEdit),    # L0C
            # (self.pbActionLabel, self.pbActionSel),                         # L1
            (self.pbAppLinkLabel, self.pbAppLinkEdit),                      # L2
            (self.pbPageURLLabel, self.pbPageURLEdit),                      # L3
            (self.pbDataNameLabel, self.pbDataNameEdit),                    # L4
            (self.pbMouseActionLabel, self.pbMouseActionSel),               # L5
            (self.pbMouseActionAmountLabel, self.pbMouseActionAmountEdit),  # L6
            (self.pbKeyboardActionLabel, self.pbKeyboardActionEdit),        # L7
            (self.pbDataFileLabel, self.pbDataFileEdit),                    # L8
            (self.pbConditionLabel, self.pbConditionEdit),                  # L9
            (self.pbConditionTrueLabel, self.pbConditionTrueEdit),          # L10
            (self.pbConditionFalseLabel, self.pbConditionFalseEdit),        # L11
            (self.pbJumpLabel, self.pbJumpEdit),                            # L12
            (self.pbRoutineLabel, self.pbRoutineEdit),                      # L13
            (self.pbExternLabel, self.pbExternEdit),                        # L14
            (self.pbWaittimeLabel, self.pbWaittimeEdit)                     # L15
        ]

        self.pbActionLayout = QtWidgets.QGridLayout()
        self.add_widgets_of_gridlayout(self.pbActionLayout, pbAction_widgets)
        self.pbActionWidget = QtWidgets.QWidget()
        self.pbActionWidget.setLayout(self.pbActionLayout)

        self.pbActionArea = QtWidgets.QScrollArea()
        self.pbActionArea.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.pbActionArea.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.pbActionArea.setWidgetResizable(True)
        self.pbActionArea.setWidget(self.pbActionWidget)
        # -------- pbsk PbAction Part End ------- #

        # -------- pbsk pbtabs Start ------ #
        self.pbtabs = QtWidgets.QTabWidget()
        self.pbtabs.addTab(self.pbInfoArea, "Feature Info")
        self.pbtabs.addTab(self.pbActionArea, "Step")
        self.pbtabs.currentChanged.connect(self.IndividualItemChanged)
        # -------- pbsk pbtabs End ------ #

        # ------- pbsk List View Start ------- #
        self.pbskALLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Anchor List:"))
        # self.pbskAnchorListView = QtWidgets.QListView()
        self.pbskAnchorListView = AnchorListView()
        self.pbskAnchorListView.installEventFilter(self)
        self.anchorListModel = QtGui.QStandardItemModel(self.pbskAnchorListView)
        self.pbskAnchorListView.setModel(self.anchorListModel)
        self.pbskAnchorListView.setViewMode(QtWidgets.QListView.IconMode)
        self.pbskAnchorListView.setMovement(QtWidgets.QListView.Snap)
        # newach = ANCHOR("abc", "image")
        # self.anchorListModel.appendRow(newach)

        self.pbskAnchorListScroll = QtWidgets.QScrollArea()
        self.pbskAnchorListScroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.pbskAnchorListScroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.pbskAnchorListScroll.setWidgetResizable(True)
        self.pbskAnchorListScroll.setWidget(self.pbskAnchorListView)

        self.pbskALLayout = QtWidgets.QVBoxLayout()
        self.pbskALLayout.addWidget(self.pbskALLabel)
        self.pbskALLayout.addWidget(self.pbskAnchorListScroll)
        self.pbskALWidget = QtWidgets.QWidget()
        self.pbskALWidget.setLayout(self.pbskALLayout)

        self.pbskDLLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Useful Data List:"))
        self.pbskDataListView = QtWidgets.QListView()
        self.pbskDataListView.installEventFilter(self)
        self.dataListModel = QtGui.QStandardItemModel(self.pbskDataListView)
        self.pbskDataListView.setModel(self.dataListModel)
        self.pbskDataListView.setViewMode(QtWidgets.QListView.ListMode)
        self.pbskDataListView.setMovement(QtWidgets.QListView.Snap)
        # newui = USER_INFO("aaa")
        # self.dataListModel.appendRow(newui)

        self.pbskDataListScroll = QtWidgets.QScrollArea()
        self.pbskDataListScroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.pbskDataListScroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.pbskDataListScroll.setWidgetResizable(True)
        self.pbskDataListScroll.setWidget(self.pbskDataListView)

        self.pbskDLLayout = QtWidgets.QVBoxLayout()
        self.pbskDLLayout.addWidget(self.pbskDLLabel)
        self.pbskDLLayout.addWidget(self.pbskDataListScroll)
        self.pbskDLWidget = QtWidgets.QWidget()
        self.pbskDLWidget.setLayout(self.pbskDLLayout)

        self.pbskSLLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Step List:"))
        self.pbskStepListView = QtWidgets.QListView()
        self.pbskStepListView.installEventFilter(self)
        self.stepListModel = QtGui.QStandardItemModel(self.pbskStepListView)
        self.pbskStepListView.setModel(self.stepListModel)
        self.pbskStepListView.setViewMode(QtWidgets.QListView.ListMode)
        self.pbskStepListView.setMovement(QtWidgets.QListView.Snap)
        # newst = PROCEDURAL_STEP("bbb")
        # self.stepListModel.appendRow(newst)

        self.pbskStepListScroll = QtWidgets.QScrollArea()
        self.pbskStepListScroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.pbskStepListScroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.pbskStepListScroll.setWidgetResizable(True)
        self.pbskStepListScroll.setWidget(self.pbskStepListView)

        self.pbskSLLayout = QtWidgets.QVBoxLayout()
        self.pbskSLLayout.addWidget(self.pbskSLLabel)
        self.pbskSLLayout.addWidget(self.pbskStepListScroll)
        self.pbskSLWidget = QtWidgets.QWidget()
        self.pbskSLWidget.setLayout(self.pbskSLLayout)
        self.pbskSLWidget.setVisible(False)
        # ------- pbsk List View End ------- #

        # ------- pbsk buttons Start ------- #
        self.IA_Remove_button = QtWidgets.QPushButton("Remove")
        self.IA_Add_button = QtWidgets.QPushButton("Add")
        self.IA_Save_button = QtWidgets.QPushButton("Save")

        self.IA_Remove_button.clicked.connect(self.ia_remove)
        self.IA_Add_button.clicked.connect(self.ia_add)
        self.IA_Save_button.clicked.connect(self.ia_save)

        self.pbskButtonsLayout = QtWidgets.QHBoxLayout()
        self.pbskButtonsLayout.addWidget(self.IA_Remove_button)
        self.pbskButtonsLayout.addWidget(self.IA_Add_button)
        self.pbskButtonsLayout.addWidget(self.IA_Save_button)

        self.pbskButtonsWidget = QtWidgets.QWidget()
        self.pbskButtonsWidget.setLayout(self.pbskButtonsLayout)
        # ------- pbsk buttons End ------- #

        self.hsplitter2 = QtWidgets.QSplitter(Qt.Vertical)
        self.hsplitter2.addWidget(self.pbtabs)
        self.hsplitter2.addWidget(self.pbskALWidget)
        self.hsplitter2.addWidget(self.pbskDLWidget)
        self.hsplitter2.addWidget(self.pbskSLWidget)
        self.hsplitter2.addWidget(self.pbskButtonsWidget)

        self.pbsklayout = QtWidgets.QVBoxLayout()
        self.pbsklayout.addWidget(self.pbsk_header_widget)
        self.pbsklayout.addWidget(self.hsplitter2)

        self.pbskWidget = QtWidgets.QWidget()
        self.pbskWidget.setLayout(self.pbsklayout)

        # ------ sk layout start ------- #
        self.skill_load_button = QtWidgets.QPushButton("Load Skill")
        self.skill_save_button = QtWidgets.QPushButton("Save Skill")
        self.skill_cancel_button = QtWidgets.QPushButton("Cancel")
        self.skill_run_button = QtWidgets.QPushButton("Trial Run")
        self.skill_step_button = QtWidgets.QPushButton("Step")
        self.skill_stop_button = QtWidgets.QPushButton("Stop")
        self.skill_resume_button = QtWidgets.QPushButton("Continue")

        self.skill_load_button.clicked.connect(self.load_skill_file)
        self.skill_save_button.clicked.connect(self.save_skill_file)
        self.skill_cancel_button.clicked.connect(self.cancel_run)
        self.skill_run_button.clicked.connect(self.trial_run)
        self.skill_step_button.clicked.connect(self.run_step)
        self.skill_stop_button.clicked.connect(self.stop_run)
        self.skill_resume_button.clicked.connect(self.continue_run)

        self.skblayout = QtWidgets.QHBoxLayout()
        self.skblayout.addWidget(self.skill_load_button)
        self.skblayout.addWidget(self.skill_run_button)
        self.skblayout.addWidget(self.skill_step_button)
        self.skblayout.addWidget(self.skill_save_button)
        self.skblayout.addWidget(self.skill_cancel_button)

        self.skFCWidget = SkFCWidget()
        self.skCodeWidget = PMGPythonEditor()

        self.skvtabs = QtWidgets.QTabWidget()
        self.skvtabs.addTab(self.skFCWidget, "Flow Chart")
        self.skvtabs.addTab(self.skCodeWidget, "Code")

        self.skconsolelabel = QtWidgets.QLabel("Console")
        self.skconsolelabel.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.skconsole = QtWidgets.QTextBrowser()
        self.consoleLayout = QtWidgets.QVBoxLayout()
        self.consoleLayout.addWidget(self.skconsolelabel)
        self.consoleLayout.addWidget(self.skconsole)

        self.consoleWidget = QtWidgets.QWidget()
        self.consoleWidget.setLayout(self.consoleLayout)

        self.hsplitter1 = QtWidgets.QSplitter(Qt.Vertical)
        self.hsplitter1.addWidget(self.skvtabs)
        self.hsplitter1.addWidget(self.consoleWidget)

        self.sklayout = QtWidgets.QVBoxLayout()
        self.sklayout.addWidget(self.hsplitter1)
        self.sklayout.addLayout(self.skblayout)

        self.skWidget = QtWidgets.QWidget()
        self.skWidget.setLayout(self.sklayout)
        # -------- sk layout end ------ #

        # ------ main layout ------- #
        self.vsplitter1 = QtWidgets.QSplitter(Qt.Horizontal)
        self.vsplitter1.addWidget(self.pbrunWidget)
        self.vsplitter1.addWidget(self.pbskWidget)
        self.vsplitter1.addWidget(self.skWidget)
        self.vsplitter1.setStretchFactor(0, 1)
        self.vsplitter1.setStretchFactor(1, 1)
        self.vsplitter1.setStretchFactor(2, 3)
        # self.vsplitter1.setChildrenCollapsible(0)
        # self.vsplitter1.setChildrenCollapsible(1)

        self.layout = QtWidgets.QHBoxLayout()
        self.layout.addWidget(self.vsplitter1)

        self.mainWidget = QtWidgets.QWidget()
        self.mainWidget.setLayout(self.layout)
        self.setCentralWidget(self.mainWidget)

        # app = QtWidgets.QApplication.instance()
        # screen = app.primaryScreen()
        # #print('Screen: %s' % screen.name())
        # size = screen.size()
        # print('Size: %d x %d' % (size.width(), size.height()))

        # self.pbview.rubberBandChanged.connect(self.select_contents)
        # self.pbscene.selectionChanged.connect(self.select_contents)

    def add_items_of_combobox(self, combobox: QComboBox, items: []):
        for item in items:
            combobox.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", item))

    def add_widgets_of_gridlayout(self, gridlayout: QGridLayout, widgets: ()):
        for i, (w1, w2) in enumerate(widgets):
            gridlayout.addWidget(w1, i, 0)
            gridlayout.addWidget(w2, i, 1)

            gridlayout.setAlignment(w1, Qt.AlignmentFlag.AlignVCenter)
            gridlayout.setAlignment(w2, Qt.AlignmentFlag.AlignVCenter)

    def set_pb_mode(self, inmode):
        self.pb_mode = inmode
        self.pbview.set_mode(inmode)

    def load_image_file(self, infile):
        self.image_qt = QtGui.QImage(infile)

        self.pixmap = QPixmap.fromImage(self.image_qt)
        # pixmap.setDevicePixelRatio(2.5)
        self.spixmap = self.pixmap.scaled(self.pixmap.size().width()/2.5, self.pixmap.size().height()/2.5, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        self.pic.setPixmap(self.spixmap)


        # unit in QT is 2.5x unit in pixel.
    def hide_app_page(self):
        self.pbAppLinkLabel.setVisible(False)
        self.pbAppLinkEdit.setVisible(False)
        self.pbPageURLLabel.setVisible(False)
        self.pbPageURLEdit.setVisible(False)

    def show_app_page(self):
        self.pbAppLinkLabel.setVisible(True)
        self.pbAppLinkEdit.setVisible(True)
        self.pbPageURLLabel.setVisible(True)
        self.pbPageURLEdit.setVisible(True)

    def hide_condition(self):
        self.pbConditionLabel.setVisible(False)
        self.pbConditionEdit.setVisible(False)
        self.pbConditionTrueLabel.setVisible(False)
        self.pbConditionTrueEdit.setVisible(False)
        self.pbConditionFalseLabel.setVisible(False)
        self.pbConditionFalseEdit.setVisible(False)

    def show_condition(self):
        self.pbConditionLabel.setVisible(True)
        self.pbConditionEdit.setVisible(True)
        self.pbConditionTrueLabel.setVisible(True)
        self.pbConditionTrueEdit.setVisible(True)
        self.pbConditionFalseLabel.setVisible(True)
        self.pbConditionFalseEdit.setVisible(True)

    def hide_routine(self):
        self.pbRoutineLabel.setVisible(False)
        self.pbRoutineEdit.setVisible(False)

    def show_routine(self):
        self.pbRoutineLabel.setVisible(True)
        self.pbRoutineEdit.setVisible(True)

    def hide_extern(self):
        self.pbExternLabel.setVisible(False)
        self.pbExternEdit.setVisible(False)

    def show_extern(self):
        self.pbExternLabel.setVisible(True)
        self.pbExternEdit.setVisible(True)

    def hide_jump(self):
        self.pbJumpLabel.setVisible(False)
        self.pbJumpEdit.setVisible(False)

    def show_jump(self):
        self.pbJumpLabel.setVisible(True)
        self.pbJumpEdit.setVisible(True)

    def hide_wait(self):
        self.pbWaittimeLabel.setVisible(False)
        self.pbWaittimeEdit.setVisible(False)

    def show_wait(self):
        self.pbWaittimeLabel.setVisible(True)
        self.pbWaittimeEdit.setVisible(True)

    def hide_mouse_action(self):
        self.pbMouseActionLabel.setVisible(False)
        self.pbMouseActionSel.setVisible(False)
        self.pbMouseActionAmountLabel.setVisible(False)
        self.pbMouseActionAmountEdit.setVisible(False)

    def show_mouse_action(self):
        self.pbMouseActionLabel.setVisible(True)
        self.pbMouseActionSel.setVisible(True)
        self.pbMouseActionAmountLabel.setVisible(True)
        self.pbMouseActionAmountEdit.setVisible(True)

    def hide_keyboard_action(self):
        self.pbKeyboardActionLabel.setVisible(False)
        self.pbKeyboardActionEdit.setVisible(False)

    def show_keyboard_action(self):
        self.pbKeyboardActionLabel.setVisible(True)
        self.pbKeyboardActionEdit.setVisible(True)

    def hide_data_name(self):
        self.pbDataNameLabel.setVisible(False)
        self.pbDataNameEdit.setVisible(False)

    def show_data_name(self):
        self.pbDataNameLabel.setVisible(True)
        self.pbDataNameEdit.setVisible(True)

    def hide_data_file(self):
        self.pbDataFileLabel.setVisible(False)
        self.pbDataFileEdit.setVisible(False)

    def show_data_file(self):
        self.pbDataFileLabel.setVisible(True)
        self.pbDataFileEdit.setVisible(True)


    # UI based on action type.
    def pbActionSel_changed(self):
        pbActionSel_text = self.pbActionSel.currentText()
        if pbActionSel_text == 'App Page Open':
            self.hide_condition()
            self.hide_data_file()
            self.hide_data_name()
            self.hide_keyboard_action()
            self.hide_mouse_action()
            self.hide_wait()
            self.hide_jump()
            self.hide_extern()
            self.hide_routine()
            self.show_app_page()
        elif pbActionSel_text == 'Create Data':
            self.hide_condition()
            self.hide_data_file()
            self.show_data_name()
            self.hide_keyboard_action()
            self.hide_mouse_action()
            self.hide_wait()
            self.hide_jump()
            self.hide_extern()
            self.hide_routine()
            self.hide_app_page()
        elif pbActionSel_text == 'Browse':
            self.hide_condition()
            self.hide_data_file()
            self.hide_data_name()
            self.hide_keyboard_action()
            self.hide_mouse_action()
            self.hide_wait()
            self.hide_jump()
            self.hide_extern()
            self.hide_routine()
            self.hide_app_page()
        elif pbActionSel_text == 'Mouse Action':
            self.hide_condition()
            self.hide_data_file()
            self.hide_data_name()
            self.hide_keyboard_action()
            self.show_mouse_action()
            self.hide_wait()
            self.hide_jump()
            self.hide_extern()
            self.hide_routine()
            self.hide_app_page()
        elif pbActionSel_text == 'Keyboard Action':
            self.hide_condition()
            self.hide_data_file()
            self.hide_data_name()
            self.show_keyboard_action()
            self.hide_mouse_action()
            self.hide_wait()
            self.hide_jump()
            self.hide_extern()
            self.hide_routine()
            self.hide_app_page()
        elif pbActionSel_text == 'Load Data':
            self.hide_condition()
            self.show_data_file()
            self.show_data_name()
            self.hide_keyboard_action()
            self.hide_mouse_action()
            self.hide_wait()
            self.hide_jump()
            self.hide_extern()
            self.hide_routine()
            self.hide_app_page()
        elif pbActionSel_text == 'Save Data':
            self.hide_condition()
            self.show_data_file()
            self.show_data_name()
            self.hide_keyboard_action()
            self.hide_mouse_action()
            self.hide_wait()
            self.hide_jump()
            self.hide_extern()
            self.hide_routine()
            self.hide_app_page()
        elif pbActionSel_text == 'Conditional Step':
            self.show_condition()
            self.hide_data_file()
            self.hide_data_name()
            self.hide_keyboard_action()
            self.hide_mouse_action()
            self.hide_wait()
            self.hide_jump()
            self.hide_extern()
            self.hide_routine()
            self.hide_app_page()
        elif pbActionSel_text == 'Jump Step':
            self.hide_condition()
            self.hide_data_file()
            self.hide_data_name()
            self.hide_keyboard_action()
            self.hide_mouse_action()
            self.hide_wait()
            self.show_jump()
            self.hide_extern()
            self.hide_routine()
            self.hide_app_page()
        elif pbActionSel_text == 'Set Wait':
            self.hide_condition()
            self.hide_data_file()
            self.hide_data_name()
            self.hide_keyboard_action()
            self.hide_mouse_action()
            self.show_wait()
            self.hide_jump()
            self.hide_extern()
            self.hide_routine()
            self.hide_app_page()
        elif pbActionSel_text == 'Run Routine':
            self.hide_condition()
            self.hide_data_file()
            self.hide_data_name()
            self.hide_keyboard_action()
            self.hide_mouse_action()
            self.hide_wait()
            self.hide_jump()
            self.hide_extern()
            self.show_routine()
            self.hide_app_page()
        elif pbActionSel_text == 'Run External':
            self.hide_condition()
            self.hide_data_file()
            self.hide_data_name()
            self.hide_keyboard_action()
            self.hide_mouse_action()
            self.hide_wait()
            self.hide_jump()
            self.show_extern()
            self.hide_routine()
            self.hide_app_page()

    def pbInfoSel_changed(self):
        if self.pbInfoSel.currentText() == 'Anchor':
            self.pbInfoNameLabel.setText("Anchor Name:")
            self.pbDTLabel.setVisible(False)
            self.pbDTSel.setVisible(False)
            self.pbNLabel.setVisible(False)
            self.pbNEdit.setVisible(False)
            self.pbRTSel.removeItem(3)
        elif self.pbInfoSel.currentText() == 'Useful Data':
            self.pbInfoNameLabel.setText("Useful Data Name:")
            self.pbDTLabel.setVisible(True)
            self.pbDTSel.setVisible(True)
            self.pbNLabel.setVisible(True)
            self.pbNEdit.setVisible(True)
            self.pbRTSel.addItem("Contain Anchors")



    def pbRTSel_changed(self):
        if self.pbRTSel.currentText() == 'No Ref':
            self.pbNRefSel.setCurrentIndex(0)
        elif self.pbRTSel.currentText() == 'By Offset':
            self.pbNRefSel.setCurrentIndex(1)
        elif self.pbRTSel.currentText() == 'By Bound Box':
            self.pbNRefSel.setCurrentIndex(2)

    def set_cloud(self, session, cog):
        self.session = session
        self.cog = cog

    def start_train(self):
        print("start training...")
        file_name = self.home_path + "resource/songc_yahoo/win/chrome_amz_main/temp/step1.png"
        self.req_train(file_name)

    def train_next_step(self):
        self.step_count = self.step_count + 1
        file_name = self.home_path + "resource/songc_yahoo/win/chrome_amz_main/temp/step" + str(self.step_count) + ".png"
        print("next step... ", self.step_count)
        self.req_train(file_name)

    def train_prev_step(self):
        self.step_count = self.step_count - 1
        file_name = self.home_path + "resource/songc_yahoo/win/amz_main/temp/step" + str(self.step_count) + ".png"
        print("prev step... ", self.step_count)
        self.req_train(file_name)

    def re_train_step(self):
        print("refresh... ", self.step_count)
        file_name = self.home_path + "resource/songc_yahoo/win/amz_main/temp/step" + str(self.step_count) + ".png"
        self.req_train(file_name)

    def remove_all_rects(self):
        for rect in self.rects:
            self.pbscene.removeItem(rect)
        self.rects = []

    def req_train(self, file_name):
        # send the screen image to S3 and send reqTrain API
        # The API will return all info on the page.
        # for remote object full path: username/os_app/site_page/task/filename.
        self.load_image_file(file_name)
        self.remove_all_rects()
        result = read_screen(file_name, bucket="winrpa")
        train_req = [{"skillName": "amz_main_browse", "skillFile": "amz_main_browse.csk", "imageFile": file_name }]
        result = req_train_read_screen(self.session, train_req, self.cog.id_token)
        print("result:", result)
        result_json = json.loads(result)
        resp = json.loads(result_json["data"]["reqTrain"])
        print("resp:", resp["body"])
        bdata = json.loads(resp["body"])
        print("bdata:", bdata["data"], "##", len(bdata["data"]))
        self.draw_rects(bdata["data"])

    def draw_rects(self, screen_contents):
        for clickable in screen_contents:
            l = float(clickable['loc'][1])/2.5
            t = float(clickable['loc'][0])/2.5
            w = (float(clickable['loc'][3]) - float(clickable['loc'][1]))/2.5
            h = (float(clickable['loc'][2]) - float(clickable['loc'][0]))/2.5

            rect = QRectF(l, t, w, h)

            if clickable["type"] == "info":
                self.pbscene.addRect(rect, self.imgBoxPen, self.brush)
            elif clickable["type"] == "anchor_icon":
                self.pbscene.addRect(rect, self.udBoxPen, self.brush)
            else:
                self.pbscene.addRect(rect, self.txtBoxPen, self.brush)
            #self.rects.append(rect)

    def select_contents(self):
        print("selected: ", self.pbview.rubberBandRect())

    def eventFilter(self, source, event):
        # print("source:", source, " event: ", event)
        if event.type() == QtCore.QEvent.ContextMenu and source is self.pbview:
            print("right clicking...")
            self.popMenu = QtWidgets.QMenu(self)
            self.setAnchorAction = self._createSetAnchorAction()
            self.setUDAction = self._createSetUDAction()
            self.clearBBAction = self._createClearBBAction()

            self.popMenu.addAction(self.setAnchorAction)
            self.popMenu.addAction(self.setUDAction)
            self.popMenu.addSeparator()
            self.popMenu.addAction(self.clearBBAction)

            selected_act = self.popMenu.exec_(event.globalPos())
            if selected_act:
                if selected_act == self.setAnchorAction:
                    print("set anchor")
                elif selected_act == self.setUDAction:
                    print("set UD")
                elif selected_act == self.clearBBAction:
                    print("clear BB", len(self.pbscene.current_items))
                    if len(self.pbscene.current_items) > 0:
                        self.pbscene.removeItem(self.pbscene.current_items[0])

            self.pb_mode = "quiet"
            self.pbview.set_mode("quiet")
            return True

        if event.type() == QtCore.QEvent.ContextMenu and source is self.pbskAnchorListView:
            #print("bot RC menu....")
            self.popMenu = QtWidgets.QMenu(self)
            self.anchorEditAction = self._createAnchorEditAction()
            self.anchorCloneAction = self._createAnchorCloneAction()
            self.anchorDeleteAction = self._createAnchorDeleteAction()

            self.popMenu.addAction(self.anchorEditAction)
            self.popMenu.addAction(self.anchorCloneAction)
            self.popMenu.addSeparator()
            self.popMenu.addAction(self.anchorDeleteAction)

            selected_act = self.popMenu.exec_(event.globalPos())
            if selected_act:
                self.selected_anchor_row = source.indexAt(event.pos()).row()
                self.selected_anchor_item = self.anchorListModel.item(self.selected_anchor_row)
                if selected_act == self.anchorEditAction:
                    self.editAnchor()
                elif selected_act == self.anchorCloneAction:
                    self.cloneAnchor()
                elif selected_act == self.anchorDeleteAction:
                    self.deleteAnchor()
            return True
        elif event.type() == QtCore.QEvent.ContextMenu and source is self.pbskDataListView:
            #print("mission RC menu....")
            self.popMenu = QtWidgets.QMenu(self)
            self.userDataEditAction = self._createUserDataEditAction()
            self.userDataCloneAction = self._createUserDataCloneAction()
            self.userDataDeleteAction = self._createUserDataDeleteAction()

            self.popMenu.addAction(self.userDataEditAction)
            self.popMenu.addAction(self.userDataCloneAction)
            self.popMenu.addSeparator()
            self.popMenu.addAction(self.userDataDeleteAction)

            selected_act = self.popMenu.exec_(event.globalPos())
            if selected_act:
                self.selected_user_data_row = source.indexAt(event.pos()).row()
                self.selected_user_data_item = self.dataListModel.item(self.selected_user_data_row)
                if selected_act == self.userDataEditAction:
                    self.editUserData()
                elif selected_act == self.userDataCloneAction:
                    self.cloneUserData()
                elif selected_act == self.userDataDeleteAction:
                    self.deleteUserData()
            return True
        elif event.type() == QtCore.QEvent.ContextMenu and source is self.pbskStepListView:
            # print("mission RC menu....")
            self.popMenu = QtWidgets.QMenu(self)
            self.stepEditAction = self._createStepEditAction()
            self.stepCloneAction = self._createStepCloneAction()
            self.stepDeleteAction = self._createStepDeleteAction()

            self.popMenu.addAction(self.stepEditAction)
            self.popMenu.addAction(self.stepCloneAction)
            self.popMenu.addSeparator()
            self.popMenu.addAction(self.stepDeleteAction)

            selected_act = self.popMenu.exec_(event.globalPos())
            if selected_act:
                self.selected_step_row = source.indexAt(event.pos()).row()
                self.selected_step_item = self.stepListModel.item(self.selected_step_row)
                if selected_act == self.stepEditAction:
                    self.editStep()
                elif selected_act == self.stepCloneAction:
                    self.cloneStep()
                elif selected_act == self.stepDeleteAction:
                    self.deleteStep()
            return True

        return super().eventFilter(source, event)

    def _createSetAnchorAction(self):
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Set Anchor"))
        return new_action

    def _createSetUDAction(self):
       new_action = QtGui.QAction(self)
       new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Set Useful Data"))
       return new_action

    def _createClearBBAction(self):
       new_action = QtGui.QAction(self)
       new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Clear Bound Box"))
       return new_action

    def formRectPos(self, start, end):
        x = start.x()
        y = start.y()
        w = abs(start.x() - end.x())
        h = abs(start.y() - end.y())
        if start.x() > end.x():
            x = end.x()

        if start.y() > end.y():
            y = end.y()

        return x, y, w, h

    def get_ref1xy(self):
        refx = {"dir": self.pbRef1XOffsetDirSel.currentText(),
                "type": self.pbRef1XOffsetTypeSel.currentText(),
                "val": self.pbRef1XOffsetValEdit.text(),
                "unit": self.pbRef1XOffsetUnitSel.currentText()}
        refy = {"dir": self.pbRef1YOffsetDirSel.currentText(),
                "type": self.pbRef1YOffsetTypeSel.currentText(),
                "val": self.pbRef1YOffsetValEdit.text(),
                "unit": self.pbRef1YOffsetUnitSel.currentText()}

        return refx, refy

    def get_ref2xy(self):
        refx = {"dir": self.pbRef2XOffsetDirSel.currentText(),
                "type": self.pbRef2XOffsetTypeSel.currentText(),
                "val": self.pbRef2XOffsetValEdit.text(),
                "unit": self.pbRef2XOffsetUnitSel.currentText()}
        refy = {"dir": self.pbRef2YOffsetDirSel.currentText(),
                "type": self.pbRef2YOffsetTypeSel.currentText(),
                "val": self.pbRef2YOffsetValEdit.text(),
                "unit": self.pbRef2YOffsetUnitSel.currentText()}

        return refx, refy

    def get_ref3xy(self):
        refx = {"dir": self.pbRef3XOffsetDirSel.currentText(),
                "type": self.pbRef3XOffsetTypeSel.currentText(),
                "val": self.pbRef3XOffsetValEdit.text(),
                "unit": self.pbRef3XOffsetUnitSel.currentText()}
        refy = {"dir": self.pbRef3YOffsetDirSel.currentText(),
                "type": self.pbRef3YOffsetTypeSel.currentText(),
                "val": self.pbRef3YOffsetValEdit.text(),
                "unit": self.pbRef3YOffsetUnitSel.currentText()}

        return refx, refy

    def get_ref4xy(self):
        refx = {"dir": self.pbRef4XOffsetDirSel.currentText(),
                "type": self.pbRef4XOffsetTypeSel.currentText(),
                "val": self.pbRef4XOffsetValEdit.text(),
                "unit": self.pbRef4XOffsetUnitSel.currentText()}
        refy = {"dir": self.pbRef4YOffsetDirSel.currentText(),
                "type": self.pbRef4YOffsetTypeSel.currentText(),
                "val": self.pbRef4YOffsetValEdit.text(),
                "unit": self.pbRef4YOffsetUnitSel.currentText()}

        return refx, refy

    def ia_add(self):
        # if this bot already exists, then, this is an update case, else this is a new bot creation case.
        self.app = self.pbskAppEdit.text()
        self.domain = self.pbskDomainEdit.text()
        self.page = self.pbskPageEdit.text()
        self.action = self.pbActionSel.currentText()
        skill_name = self.app + "_" + self.domain + "_" + self.page
        if self.pbtabs.currentIndex() == 0:
            if self.pbInfoSel.currentText() == "Anchor":
                print("add a new anchor....")
                self.newAnchor = ANCHOR(self.pbInfoNameEdit.text(), self.pbATSel.currentText())
                if self.newAnchor.get_type() == "Image":
                    skill_name = ""
                    img_path = INSTALLED_PATH + USER_DIR + OS_DIR + PAGE_DIR + "/skills/" + skill_name + "/images/" + self.newAnchor.getName() + ".png"
                    self.newAnchor.set_img(img_path)
                    #now save image.
                    #area = (400, 400, 800, 800)
                    #original_img.crop(area).save(img_path, format="png")

                self.newAnchor.set_ref_method(self.pbRTSel.currentText())

                if self.pbNRefSel.currentText == '1':
                    refx, refy = self.get_ref1xy()
                    self.newAnchor.add_ref(self.pbRef1NameEdit.text(), refx, refy)
                elif self.pbNRefSel.currentText == '2':
                    refx, refy = self.get_ref1xy()
                    self.newAnchor.add_ref(self.pbRef1NameEdit.text(), refx, refy)
                    refx, refy = self.get_ref2xy()
                    self.newAnchor.add_ref(self.pbRef2NameEdit.text(), refx, refy)
                elif self.pbNRefSel.currentText == '3':
                    refx, refy = self.get_ref1xy()
                    self.newAnchor.add_ref(self.pbRef1NameEdit.text(), refx, refy)
                    refx, refy = self.get_ref2xy()
                    self.newAnchor.add_ref(self.pbRef2NameEdit.text(), refx, refy)
                    refx, refy = self.get_ref3xy()
                    self.newAnchor.add_ref(self.pbRef3NameEdit.text(), refx, refy)
                elif self.pbNRefSel.currentText == '4':
                    refx, refy = self.get_ref1xy()
                    self.newAnchor.add_ref(self.pbRef1NameEdit.text(), refx, refy)
                    refx, refy = self.get_ref2xy()
                    self.newAnchor.add_ref(self.pbRef2NameEdit.text(), refx, refy)
                    refx, refy = self.get_ref3xy()
                    self.newAnchor.add_ref(self.pbRef3NameEdit.text(), refx, refy)
                    refx, refy = self.get_ref4xy()
                    self.newAnchor.add_ref(self.pbRef4NameEdit.text(), refx, refy)
                    print("ready to add....")
                self.anchorListModel.appendRow(self.newAnchor)
            elif self.pbInfoSel.currentText() == "Useful Data":
                print("add a new user info....")
                self.newUserInfo = USER_INFO(self.pbInfoNameEdit.text())
                self.newUserInfo.set_type(self.pbDTSel.currentText())
                self.newUserInfo.set_nlines(self.pbNEdit.text())
                self.newUserInfo.set_ref_method(self.pbRTSel.currentText())
                pbNRefSel_text = self.pbNRefSel.currentText
                if pbNRefSel_text == '1':
                    refx, refy = self.get_ref1xy()
                    self.newUserInfo.add_ref(self.pbRef1NameEdit.text(), refx, refy)
                elif pbNRefSel_text == '2':
                    refx, refy = self.get_ref1xy()
                    self.newUserInfo.add_ref(self.pbRef1NameEdit.text(), refx, refy)
                    refx, refy = self.get_ref2xy()
                    self.newUserInfo.add_ref(self.pbRef2NameEdit.text(), refx, refy)
                elif pbNRefSel_text == '3':
                    refx, refy = self.get_ref1xy()
                    self.newUserInfo.add_ref(self.pbRef1NameEdit.text(), refx, refy)
                    refx, refy = self.get_ref2xy()
                    self.newUserInfo.add_ref(self.pbRef2NameEdit.text(), refx, refy)
                    refx, refy = self.get_ref3xy()
                    self.newUserInfo.add_ref(self.pbRef3NameEdit.text(), refx, refy)
                elif pbNRefSel_text == '4':
                    refx, refy = self.get_ref1xy()
                    self.newUserInfo.add_ref(self.pbRef1NameEdit.text(), refx, refy)
                    refx, refy = self.get_ref2xy()
                    self.newUserInfo.add_ref(self.pbRef2NameEdit.text(), refx, refy)
                    refx, refy = self.get_ref3xy()
                    self.newUserInfo.add_ref(self.pbRef3NameEdit.text(), refx, refy)
                    refx, refy = self.get_ref4xy()
                    self.newUserInfo.add_ref(self.pbRef4NameEdit.text(), refx, refy)
                self.dataListModel.appendRow(self.newUserInfo)

        elif self.pbtabs.currentIndex() == 1:
            print("add a new step....")
            pbActionSel_text = self.pbActionSel.currentText()
            new_step = PROCEDURAL_STEP(pbActionSel_text)
            if pbActionSel_text == 'App Page Open':
                new_step.set_app_page(self.pbAppLinkEdit.text(), self.pbPageURLEdit.text())
            elif pbActionSel_text == 'Create Data':
                new_step.set_data_name(self.pbDataNameEdit.text())
            elif pbActionSel_text == 'Mouse Action':
                new_step.set_mouse_action(self.pbMouseActionSel.currentText(), self.pbMouseActionAmountEdit.text())
            elif pbActionSel_text == 'Keyboard Action':
                new_step.set_keyboard_action(self.pbKeyboardActionEdit.text())
            elif pbActionSel_text == 'Load Data':
                new_step.set_data_file(self.pbDataFileEdit.text())
            elif pbActionSel_text == 'Save Data':
                new_step.set_data_file(self.pbDataFileEdit.text())
            elif pbActionSel_text == 'Conditional Step':
                new_step.set_condition_jump(self.pbConditionEdit.text(), self.pbConditionTrueEdit.text(), self.pbConditionFalseEdit.text())
            elif pbActionSel_text == 'Jump Step':
                new_step.set_jump(self.pbJumpEdit.text())
            elif pbActionSel_text == 'Set Wait':
                new_step.set_wait(self.pbWaittimeEdit.text())
            elif pbActionSel_text == 'Run Routine':
                new_step.set_routine(self.pbRoutineEdit.text())
            elif pbActionSel_text == 'Run External':
                new_step.set_extern(self.pbExternEdit.text())
            self.stepListModel.appendRow(new_step)

    def ia_save(self):
        print("save anchors to files....")
        # save the json
        privacy = "public"
        if privacy == "public":
            pdir = "public"
            owner = "public"
        else:
            pdir = "my"
            owner = self.parent.user

        sk_prefix = self.parent.platform + "_" + self.pbskAppEdit.text() + "_" + self.pbskDomainEdit.text() + "_" + self.pbskPageEdit.text()

        sk_json = {
            "name": self.pbActionSel.currentText(),
            "skid": 0,
            "owner": owner,
            "price": 0,
            "price_model": "free",
            "privacy": privacy,
            "path": "resource/skills/" + pdir + "/",
            "platform": self.parent.platform,
            "app": self.pbskAppEdit.text(),
            "app_link": self.pbskAppExeEdit.text(),
            "app_args": "",
            "site_name": self.pbskDomainEdit.text(),
            "site": self.pbskDomainURLEdit.text(),
            "page": self.pbskPageEdit.text(),
            "private_skill": {
                "nameSpace": "",
                "runStepsFile": "",
                "runConfig": {}
            },
            "cloud_skill": {
                "path": pdir + "/" + sk_prefix + "/" + self.pbActionSel.currentText()
            }
        }

        skj_path = self.home_path + "/resource/skills/" + pdir + "/" + sk_prefix + "/" + self.pbActionSel.currentText() + ".json"
        try:
            with open(skj_path, 'w') as f:
                json.dump(sk_json, f)
            # self.rebuildHTML()
        except IOError:
            QtGui.QMessageBox.information(
                self,
                "Unable to open file: %s" % skj_path
            )


        # save image anchor to file.
        model = self.pbskAnchorListView.model()
        for index in range(model.rowCount()):
            anchor_item = model.item(index)
            aj = self.gen_anchor_json(anchor_item)
            if aj["anchor_type"] == "icon":
                #save image to a file.
                aname = anchor_item.get_name() + ".png"

                # assume only 1 rect will be selected.
                selected_rect = self.pbview.scene().selectedItems()[0].rect()
                left = selected_rect.left()  # Replace 'l' with the x-coordinate of the upper left corner
                top = selected_rect.top()  # Replace 't' with the y-coordinate of the upper left corner
                right = selected_rect.right()  # Replace 'x' with the width of the subimage
                bottom = selected_rect.bottom()  # Replace 'y' with the height of the subimage

                # get the 1st image on image queue.
                imq = self.parent.trainNewSkillWin.imq
                original_image = imq[len(imq)-1]
                # Crop the image
                anchor_image = original_image.crop((left, top, right, bottom))
                anchor_image.save(aname, "PNG")


        # save info and anchors to csk file.
        model = self.pbskDataListView.model()
        for index in range(model.rowCount()):
            info_item = model.item(index)
            ij = self.gen_info_json(info_item)


    def gen_anchor_json(self, aitem):
        ajson = {
            "anchor_name": aitem.get_name(),
            "anchor_type": "text",
            "template": "Password",
            "ref_method": "0",
            "ref_constraints": []
        }
        return ajson

    def gen_info_json(self, iitem):
        ijson = {

        }
        return ijson

    def ia_remove(self):
        print("remove a piece of information....")
        # if this bot already exists, then, this is an update case, else this is a new bot creation case.
        if self.pbtabs.currentIndex() == 0:
            if self.pbInfoSel.currentText() == "Anchor":
                self.newAnchor = ANCHOR(self.pbInfoNameEdit.text())
                self.pbRTSel.currentIndex
                self.pbRTSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "No Ref"))
                self.pbRTSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "By Offset"))
                self.pbRTSel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "By Bound Box"))

            elif self.pbInfoSel.currentText() == "Useful Data":
                self.newUserInfo = USER_INFO(self.pbInfoNameEdit.text())
        elif self.pbtabs.currentIndex() == 1:
            print("hohoho")

    def show_ref1(self, visible: bool):
        self.pbRef1NameLabel.setVisible(visible)
        self.pbRef1NameEdit.setVisible(visible)
        self.pbRef1XOffsetDirLabel.setVisible(visible)
        self.pbRef1XOffsetDirSel.setVisible(visible)
        self.pbRef1XOffsetTypeLabel.setVisible(visible)
        self.pbRef1XOffsetTypeSel.setVisible(visible)
        self.pbRef1XOffsetValLabel.setVisible(visible)
        self.pbRef1XOffsetValEdit.setVisible(visible)
        self.pbRef1XOffsetUnitLabel.setVisible(visible)
        self.pbRef1XOffsetUnitSel.setVisible(visible)
        self.pbRef1YOffsetDirLabel.setVisible(visible)
        self.pbRef1YOffsetDirSel.setVisible(visible)
        self.pbRef1YOffsetTypeLabel.setVisible(visible)
        self.pbRef1YOffsetTypeSel.setVisible(visible)
        self.pbRef1YOffsetValLabel.setVisible(visible)
        self.pbRef1YOffsetValEdit.setVisible(visible)
        self.pbRef1YOffsetUnitLabel.setVisible(visible)
        self.pbRef1YOffsetUnitSel.setVisible(visible)

    def show_ref2(self, visible: bool):
        self.pbRef2NameLabel.setVisible(visible)
        self.pbRef2NameEdit.setVisible(visible)
        self.pbRef2XOffsetDirLabel.setVisible(visible)
        self.pbRef2XOffsetDirSel.setVisible(visible)
        self.pbRef2XOffsetTypeLabel.setVisible(visible)
        self.pbRef2XOffsetTypeSel.setVisible(visible)
        self.pbRef2XOffsetValLabel.setVisible(visible)
        self.pbRef2XOffsetValEdit.setVisible(visible)
        self.pbRef2XOffsetUnitLabel.setVisible(visible)
        self.pbRef2XOffsetUnitSel.setVisible(visible)
        self.pbRef2YOffsetDirLabel.setVisible(visible)
        self.pbRef2YOffsetDirSel.setVisible(visible)
        self.pbRef2YOffsetTypeLabel.setVisible(visible)
        self.pbRef2YOffsetTypeSel.setVisible(visible)
        self.pbRef2YOffsetValLabel.setVisible(visible)
        self.pbRef2YOffsetValEdit.setVisible(visible)
        self.pbRef2YOffsetUnitLabel.setVisible(visible)
        self.pbRef2YOffsetUnitSel.setVisible(visible)

    def show_ref3(self, visible: bool):
        self.pbRef3NameLabel.setVisible(visible)
        self.pbRef3NameEdit.setVisible(visible)
        self.pbRef3XOffsetDirLabel.setVisible(visible)
        self.pbRef3XOffsetDirSel.setVisible(visible)
        self.pbRef3XOffsetTypeLabel.setVisible(visible)
        self.pbRef3XOffsetTypeSel.setVisible(visible)
        self.pbRef3XOffsetValLabel.setVisible(visible)
        self.pbRef3XOffsetValEdit.setVisible(visible)
        self.pbRef3XOffsetUnitLabel.setVisible(visible)
        self.pbRef3XOffsetUnitSel.setVisible(visible)
        self.pbRef3YOffsetDirLabel.setVisible(visible)
        self.pbRef3YOffsetDirSel.setVisible(visible)
        self.pbRef3YOffsetTypeLabel.setVisible(visible)
        self.pbRef3YOffsetTypeSel.setVisible(visible)
        self.pbRef3YOffsetValLabel.setVisible(visible)
        self.pbRef3YOffsetValEdit.setVisible(visible)
        self.pbRef3YOffsetUnitLabel.setVisible(visible)
        self.pbRef3YOffsetUnitSel.setVisible(visible)

    def show_ref4(self, visible: bool):
        self.pbRef4NameLabel.setVisible(visible)
        self.pbRef4NameEdit.setVisible(visible)
        self.pbRef4XOffsetDirLabel.setVisible(visible)
        self.pbRef4XOffsetDirSel.setVisible(visible)
        self.pbRef4XOffsetTypeLabel.setVisible(visible)
        self.pbRef4XOffsetTypeSel.setVisible(visible)
        self.pbRef4XOffsetValLabel.setVisible(visible)
        self.pbRef4XOffsetValEdit.setVisible(visible)
        self.pbRef4XOffsetUnitLabel.setVisible(visible)
        self.pbRef4XOffsetUnitSel.setVisible(visible)
        self.pbRef4YOffsetDirLabel.setVisible(visible)
        self.pbRef4YOffsetDirSel.setVisible(visible)
        self.pbRef4YOffsetTypeLabel.setVisible(visible)
        self.pbRef4YOffsetTypeSel.setVisible(visible)
        self.pbRef4YOffsetValLabel.setVisible(visible)
        self.pbRef4YOffsetValEdit.setVisible(visible)
        self.pbRef4YOffsetUnitLabel.setVisible(visible)
        self.pbRef4YOffsetUnitSel.setVisible(visible)

    def pbStepPrevNextSel_changed(self):
        if self.pbStepPrevNextSel.currentIndex() == 0:
            self.pbStepPrevNextNameLabel.setText(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Previous Step Name:"))
        else:
            self.pbStepPrevNextNameLabel.setText(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Next Step Name:"))

    def pbNRefSel_changed(self):
        pbNRefSel_index = self.pbNRefSel.currentIndex()
        if pbNRefSel_index == 0:
            self.show_ref1(False)
            self.show_ref2(False)
            self.show_ref3(False)
            self.show_ref4(False)
        elif pbNRefSel_index == 1:
            self.show_ref1(True)
            self.show_ref2(False)
            self.show_ref3(False)
            self.show_ref4(False)
        elif pbNRefSel_index == 2:
            self.show_ref1(True)
            self.show_ref2(True)
            self.show_ref3(False)
            self.show_ref4(False)
        elif pbNRefSel_index == 3:
            self.show_ref1(True)
            self.show_ref2(True)
            self.show_ref3(True)
            self.show_ref4(False)
        elif pbNRefSel_index == 4:
            self.show_ref1(True)
            self.show_ref2(True)
            self.show_ref3(True)
            self.show_ref4(True)

    def IndividualItemChanged(self):
        if self.pbtabs.currentIndex() == 0:
            # user click on Info Tab
            self.IA_Add_button.setText(QtWidgets.QApplication.translate("QtWidgets.QPushButton", "Add Feature"))
            self.IA_Remove_button.setText(QtWidgets.QApplication.translate("QtWidgets.QPushButton", "Remove CSK"))
            self.IA_Save_button.setText(QtWidgets.QApplication.translate("QtWidgets.QPushButton", "Save CSK"))
            self.pbskALWidget.setVisible(True)
            self.pbskDLWidget.setVisible(True)
            self.pbskSLWidget.setVisible(False)

        elif self.pbtabs.currentIndex() == 1:
            # user click on Step Tab
            self.pbskALWidget.setVisible(False)
            self.pbskDLWidget.setVisible(False)
            self.pbskSLWidget.setVisible(True)
            self.IA_Add_button.setText(QtWidgets.QApplication.translate("QtWidgets.QPushButton", "Add Step"))
            self.IA_Remove_button.setText(QtWidgets.QApplication.translate("QtWidgets.QPushButton", "Remove Step"))
            self.IA_Save_button.setText(QtWidgets.QApplication.translate("QtWidgets.QPushButton", "Save Step"))

    def load_skill_file(self):
        # bring out the load file dialog
        pskFile = self.skfsel.getOpenFileName()

    def save_skill_file(self):
        # bring out the load file dialog
        pskFile = self.skfsel.getSaveFileName()

    def cancel_run(self):
        #will add later a sure? dialog
        cancelRun()

    def stop_run(self):
        #will add later a sure? dialog
        pauseRun()

    def trial_run(self):
        # self.runStopped = False
        all_skill_codes = [{"ns": "B0M1225!!", "skfile": "trial run skill psk file name full path here"}]
        rpa_script = prepRunSkill(all_skill_codes)

        self.parent.addSkillToTrialRunMission(0)          # replace 0 with the trial run skill ID
        trMission = self.parent.getTrialRunMission()
        # runAllSteps(self.currentSkill.get_steps())
        runResult = runAllSteps(rpa_script, trMission, thisTrialRUNSkill)   # thisTrialRunSkill is the pointer to WORKSKILL created on this GUI.
        psk_words = self.skFCWidget.skfc_scene.gen_psk_words()

        # file = app_info.appdata_temp_path + "/test_mouse_sroll.psk"
        # skf = open(file, "w")
        # skf.write("\n")
        #
        # skf.write(psk_words)
        # skf.close()
        #
        # print("done generating skill============================>")
        # skodes = [{"ns": "TestMouseScrollSK", "skfile": file}]
        # rpa_script = prepRunSkill(skodes)
        # print("done all address gen.................")
        #
        # runAllSteps(rpa_script, None, None)

    def continue_run(self):
        continueRun(steps, last_step)

    def run_step(self):
        continueRun(steps, last_step)

    def _createAnchorEditAction(self):
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Edit"))
        return new_action

    def _createAnchorCloneAction(self):
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Clone"))
        return new_action

    def _createAnchorDeleteAction(self):
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Delete"))
        return new_action

    def _createUserDataEditAction(self):
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Edit"))
        return new_action

    def _createUserDataCloneAction(self):
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Clone"))
        return new_action

    def _createUserDataDeleteAction(self):
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Delete"))
        return new_action

    def _createStepEditAction(self):
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Edit"))
        return new_action

    def _createStepCloneAction(self):
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Clone"))
        return new_action

    def _createStepDeleteAction(self):
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Delete"))
        return new_action

    def editAnchor(self):
        print("edit anchor")

    def cloneAnchor(self):
        print("clone anchor")

    def deleteAnchor(self):
        # File actions
        msgBox = QtWidgets.QMessageBox()
        QtWidgets.QApplication.translate("QtWidgets.QMessageBox", "Are you sure about deleting this anchor?")
        msgBox.setText(QtWidgets.QApplication.translate("QtWidgets.QMessageBox", "The anchor will be removed and won't be able recover from it.."))
        msgBox.setInformativeText(QtWidgets.QApplication.translate("QtWidgets.QMessageBox", "Are you sure about deleting this anchor?"))
        msgBox.setStandardButtons(QtWidgets.QMessageBox.Cancel | QtWidgets.QMessageBox.Yes)
        msgBox.setDefaultButton(QtWidgets.QMessageBox.Yes)
        ret = msgBox.exec_()

        if ret == QtWidgets.QMessageBox.Yes:
            api_removes = []
            items = [self.selected_anchor_item]
            if len(items):
                for item in items:
                    # remove file first, then the item in the model.
                    # shutil.rmtree(temp_page_dir)
                    # os.remove(full_temp_page)

                    # remove the local data and GUI.
                    self.anchorListModel.removeRow(item.row())

        #self.botModel.removeRow(self.selected_bot_row)
        #print("delete bot" + str(self.selected_bot_row))

    def editUserData(self):
        print("edit user data")

    def cloneUserData(self):
        print("clone user data")

    def deleteUserData(self):
        # File actions
        msgBox = QtWidgets.QMessageBox()
        msgBox.setText(QtWidgets.QApplication.translate("QtWidgets.QMessageBox", "The step will be removed and won't be able recover from it.."))
        msgBox.setInformativeText(QtWidgets.QApplication.translate("QtWidgets.QMessageBox", "Are you sure about deleting this step?"))
        msgBox.setStandardButtons(QtWidgets.QMessageBox.Cancel | QtWidgets.QMessageBox.Yes)
        msgBox.setDefaultButton(QtWidgets.QMessageBox.Yes)
        ret = msgBox.exec_()

        if ret == QtWidgets.QMessageBox.Yes:
            api_removes = []
            items = [self.selected_user_data_item]
            if len(items):
                for item in items:
                    # remove file first, then the item in the model.
                    # shutil.rmtree(temp_page_dir)
                    # os.remove(full_temp_page)

                    # remove the local data and GUI.
                    self.dataListModel.removeRow(item.row())

        #self.botModel.removeRow(self.selected_bot_row)
        #print("delete bot" + str(self.selected_bot_row))

    def editStep(self):
        print("edit step")

    def cloneStep(self):
        print("clone step")

    def deleteStep(self):
        # File actions
        msgBox = QtWidgets.QMessageBox()
        msgBox.setText(QtWidgets.QApplication.translate("QtWidgets.QMessageBox", "The step will be removed and won't be able recover from it.."))
        msgBox.setInformativeText(QtWidgets.QApplication.translate("QtWidgets.QMessageBox", "Are you sure about deleting this step?"))
        msgBox.setStandardButtons(QtWidgets.QMessageBox.Cancel | QtWidgets.QMessageBox.Yes)
        msgBox.setDefaultButton(QtWidgets.QMessageBox.Yes)
        ret = msgBox.exec_()

        if ret == QtWidgets.QMessageBox.Yes:
            api_removes = []
            items = [self.selected_step_item]
            if len(items):
                for item in items:
                    # remove file first, then the item in the model.
                    # shutil.rmtree(temp_page_dir)
                    # os.remove(full_temp_page)

                    # remove the local data and GUI.
                    self.stepListModel.removeRow(item.row())

        #self.botModel.removeRow(self.selected_bot_row)
        #print("delete bot" + str(self.selected_bot_row))

    def appDomainPage_changed(self):
        # when app, domain, page changed, that means, we need a different .csk file.
        print("app, domain, page changed....")



