import sys
import random
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene
from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainterPath, QPen, QColor
from locale import getdefaultlocale

import ctypes as ct
# from ctypes import wintypes as wt
import time
import json

from pynput import mouse
from pynput import keyboard
import threading

import pyautogui
from Cloud import *
import pyqtgraph
from pyqtgraph import flowchart
import BorderLayout
from gui.diagram.pyq_diagram import *
from WorkSkill import *
from readSkill import *
# from codeeditor import *
from gui.qtpyeditor.codeeditor.pythoneditor import PMGPythonEditor


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




class SkillGUI(QtWidgets.QMainWindow):
    def __init__(self, parent):
        super(SkillGUI, self).__init__(parent)

    # def __init__(self):
    #     super().__init__()
        self.newSkill = None
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

        self.mainWidget = QtWidgets.QWidget()

        self.vsplitter1 = QtWidgets.QSplitter(Qt.Horizontal)
        self.hsplitter1 = QtWidgets.QSplitter(Qt.Vertical)
        self.vsplitter2 = QtWidgets.QSplitter(Qt.Horizontal)
        self.hsplitter2 = QtWidgets.QSplitter(Qt.Vertical)

        self.step_count = 0
        self.step_names = []

        self.pbtabs = QtWidgets.QTabWidget()

        self.playback_start_button = QtWidgets.QPushButton("Start Payback")
        self.playback_start_button.clicked.connect(self.start_train)
        self.playback_next_button = QtWidgets.QPushButton("Next")
        self.playback_next_button.clicked.connect(self.train_next_step)
        self.playback_back_button = QtWidgets.QPushButton("Back")
        self.playback_back_button.clicked.connect(self.train_prev_step)
        self.playback_reload_button = QtWidgets.QPushButton("Refresh")
        self.playback_reload_button.clicked.connect(self.re_train_step)
        self.pbmainwin = QtWidgets.QScrollArea()
        self.pbmainwin.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.pbmainwin.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)

        self.pic = QtWidgets.QGraphicsPixmapItem()
        file_name = "C:/Users/Teco/PycharmProjects/ecbot/resource/skills/temp/step1.png"
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

        self.pbInfoWidget = QWidget()
        self.pbInfoLayout = QtWidgets.QVBoxLayout(self)
        self.pbInfoLayout.setAlignment(Qt.AlignTop)

        self.pbInfoLabel = QtWidgets.QLabel("Info Type: ", alignment=QtCore.Qt.AlignLeft)
        self.pbInfoSel = QtWidgets.QComboBox()
        self.pbInfoSel.addItem('Anchor')
        self.pbInfoSel.addItem('Useful Data')
        self.pbInfoSel.currentTextChanged.connect(self.pbInfoSel_changed)

        self.pbRTLabel = QtWidgets.QLabel("Ref. Type: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRTSel = QtWidgets.QComboBox()
        self.pbRTSel.addItem('No Ref')
        self.pbRTSel.addItem('By Offset')
        self.pbRTSel.addItem('By Bound Box')
        self.pbRTSel.currentTextChanged.connect(self.pbRTSel_changed)

        self.pbNRefLabel = QtWidgets.QLabel("# of Refs: ", alignment=QtCore.Qt.AlignLeft)
        self.pbNRefSel = QtWidgets.QComboBox()
        self.pbNRefSel.addItem('0')
        self.pbNRefSel.addItem('1')
        self.pbNRefSel.addItem('2')
        self.pbNRefSel.addItem('3')
        self.pbNRefSel.addItem('4')
        self.pbNRefSel.currentTextChanged.connect(self.pbNRefSel_changed)


        self.pbATLabel = QtWidgets.QLabel("Anchor Type: ", alignment=QtCore.Qt.AlignLeft)
        self.pbATSel = QtWidgets.QComboBox()
        self.pbATSel.addItem('Text')
        self.pbATSel.addItem('Image')

        self.pbDTLabel = QtWidgets.QLabel("Data Type: ", alignment=QtCore.Qt.AlignLeft)
        self.pbDTSel = QtWidgets.QComboBox()
        self.pbDTSel.addItem('Paragraph')
        self.pbDTSel.addItem('Lines')
        self.pbDTSel.addItem('Words')

        self.pbNLabel = QtWidgets.QLabel("# of Lines: ", alignment=QtCore.Qt.AlignLeft)
        self.pbNEdit = QtWidgets.QLineEdit()
        self.pbNEdit.setPlaceholderText("type number of lines here")

        self.pbInfoNameLabel = QtWidgets.QLabel("Name: ", alignment=QtCore.Qt.AlignLeft)
        self.pbInfoNameEdit = QtWidgets.QLineEdit()
        self.pbInfoNameEdit.setPlaceholderText("Ex: abc")

        # ----------  reference 1 widgets ----------------------------
        self.pbRef1NameLabel = QtWidgets.QLabel("Ref1 Name: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef1NameEdit = QtWidgets.QLineEdit()
        self.pbRef1NameEdit.setPlaceholderText("Ex: abc")

        self.pbRef1XOffsetDirLabel = QtWidgets.QLabel("Ref1 X Offset Dir: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef1XOffsetDirSel = QtWidgets.QComboBox()
        self.pbRef1XOffsetDirSel.addItem('Within')
        self.pbRef1XOffsetDirSel.addItem('Beyond')

        self.pbRef1XOffsetTypeLabel = QtWidgets.QLabel("Ref1 X Offset Type: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef1XOffsetTypeSel = QtWidgets.QComboBox()
        self.pbRef1XOffsetTypeSel.addItem('Absolute')
        self.pbRef1XOffsetTypeSel.addItem('Signed')
        self.pbRef1XOffsetTypeSel.addItem('Absolute Percent')
        self.pbRef1XOffsetTypeSel.addItem('Signed Percent')

        self.pbRef1XOffsetValLabel = QtWidgets.QLabel("Ref1 X Offset Value: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef1XOffsetValEdit = QtWidgets.QLineEdit()
        self.pbRef1XOffsetValEdit.setPlaceholderText("Ex: 1")

        self.pbRef1XOffsetUnitLabel = QtWidgets.QLabel("Ref1 X Offset Unit: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef1XOffsetUnitSel = QtWidgets.QComboBox()
        self.pbRef1XOffsetUnitSel.addItem('Pixel')
        self.pbRef1XOffsetUnitSel.addItem('Letter Height')
        self.pbRef1XOffsetUnitSel.addItem('Image Height')
        self.pbRef1XOffsetUnitSel.addItem('Full Height')
        self.pbRef1XOffsetUnitSel.addItem('Letter Width')
        self.pbRef1XOffsetUnitSel.addItem('Image Width')
        self.pbRef1XOffsetUnitSel.addItem('Full Width')

        self.pbRef1YOffsetDirLabel = QtWidgets.QLabel("Ref1 Y Dir: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef1YOffsetDirSel = QtWidgets.QComboBox()
        self.pbRef1YOffsetDirSel.addItem('Within')
        self.pbRef1YOffsetDirSel.addItem('Beyond')

        self.pbRef1YOffsetTypeLabel = QtWidgets.QLabel("Ref1 Y Offset Type: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef1YOffsetTypeSel = QtWidgets.QComboBox()
        self.pbRef1YOffsetTypeSel.addItem('Absolute')
        self.pbRef1YOffsetTypeSel.addItem('Signed')
        self.pbRef1YOffsetTypeSel.addItem('Absolute Percent')
        self.pbRef1YOffsetTypeSel.addItem('Signed Percent')

        self.pbRef1YOffsetValLabel = QtWidgets.QLabel("Ref1 Y Offset Value: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef1YOffsetValEdit = QtWidgets.QLineEdit()
        self.pbRef1YOffsetValEdit.setPlaceholderText("Ex: 1")

        self.pbRef1YOffsetUnitLabel = QtWidgets.QLabel("Ref1 Y Offset Unit: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef1YOffsetUnitSel = QtWidgets.QComboBox()
        self.pbRef1YOffsetUnitSel.addItem('Pixel')
        self.pbRef1YOffsetUnitSel.addItem('Letter Height')
        self.pbRef1YOffsetUnitSel.addItem('Image Height')
        self.pbRef1YOffsetUnitSel.addItem('Full Height')
        self.pbRef1YOffsetUnitSel.addItem('Letter Width')
        self.pbRef1YOffsetUnitSel.addItem('Image Width')
        self.pbRef1YOffsetUnitSel.addItem('Full Width')

        #  ----------  reference 2 widgets ----------------------------
        self.pbRef2NameLabel = QtWidgets.QLabel("Ref2 Name: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef2NameEdit = QtWidgets.QLineEdit()
        self.pbRef2NameEdit.setPlaceholderText("Ex: abc")

        self.pbRef2XOffsetDirLabel = QtWidgets.QLabel("Ref2 X Offset Dir: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef2XOffsetDirSel = QtWidgets.QComboBox()
        self.pbRef2XOffsetDirSel.addItem('Within')
        self.pbRef2XOffsetDirSel.addItem('Beyond')

        self.pbRef2XOffsetTypeLabel = QtWidgets.QLabel("Ref2 X Offset Type: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef2XOffsetTypeSel = QtWidgets.QComboBox()
        self.pbRef2XOffsetTypeSel.addItem('Absolute')
        self.pbRef2XOffsetTypeSel.addItem('Signed')
        self.pbRef2XOffsetTypeSel.addItem('Absolute Percent')
        self.pbRef2XOffsetTypeSel.addItem('Signed Percent')

        self.pbRef2XOffsetValLabel = QtWidgets.QLabel("Ref2 X Offset Value: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef2XOffsetValEdit = QtWidgets.QLineEdit()
        self.pbRef2XOffsetValEdit.setPlaceholderText("Ex: 1")

        self.pbRef2XOffsetUnitLabel = QtWidgets.QLabel("Ref2 X Offset Unit: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef2XOffsetUnitSel = QtWidgets.QComboBox()
        self.pbRef2XOffsetUnitSel.addItem('Pixel')
        self.pbRef2XOffsetUnitSel.addItem('Letter Height')
        self.pbRef2XOffsetUnitSel.addItem('Image Height')
        self.pbRef2XOffsetUnitSel.addItem('Full Height')
        self.pbRef2XOffsetUnitSel.addItem('Letter Width')
        self.pbRef2XOffsetUnitSel.addItem('Image Width')
        self.pbRef2XOffsetUnitSel.addItem('Full Width')

        self.pbRef2YOffsetDirLabel = QtWidgets.QLabel("Ref2 Y Dir: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef2YOffsetDirSel = QtWidgets.QComboBox()
        self.pbRef2YOffsetDirSel.addItem('Within')
        self.pbRef2YOffsetDirSel.addItem('Beyond')

        self.pbRef2YOffsetTypeLabel = QtWidgets.QLabel("Ref2 Y Offset Type: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef2YOffsetTypeSel = QtWidgets.QComboBox()
        self.pbRef2YOffsetTypeSel.addItem('Absolute')
        self.pbRef2YOffsetTypeSel.addItem('Signed')
        self.pbRef2YOffsetTypeSel.addItem('Absolute Percent')
        self.pbRef2YOffsetTypeSel.addItem('Signed Percent')

        self.pbRef2YOffsetValLabel = QtWidgets.QLabel("Ref2 Y Offset Value: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef2YOffsetValEdit = QtWidgets.QLineEdit()
        self.pbRef2YOffsetValEdit.setPlaceholderText("Ex: 1")

        self.pbRef2YOffsetUnitLabel = QtWidgets.QLabel("Ref2 Y Offset Unit: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef2YOffsetUnitSel = QtWidgets.QComboBox()
        self.pbRef2YOffsetUnitSel.addItem('Pixel')
        self.pbRef2YOffsetUnitSel.addItem('Letter Height')
        self.pbRef2YOffsetUnitSel.addItem('Image Height')
        self.pbRef2YOffsetUnitSel.addItem('Full Height')
        self.pbRef2YOffsetUnitSel.addItem('Letter Width')
        self.pbRef2YOffsetUnitSel.addItem('Image Width')
        self.pbRef2YOffsetUnitSel.addItem('Full Width')

        #  ----------  reference 3 widgets ----------------------------
        self.pbRef3NameLabel = QtWidgets.QLabel("Ref3 Name: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef3NameEdit = QtWidgets.QLineEdit()
        self.pbRef3NameEdit.setPlaceholderText("Ex: abc")

        self.pbRef3XOffsetDirLabel = QtWidgets.QLabel("Ref3 X Offset Dir: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef3XOffsetDirSel = QtWidgets.QComboBox()
        self.pbRef3XOffsetDirSel.addItem('Within')
        self.pbRef3XOffsetDirSel.addItem('Beyond')

        self.pbRef3XOffsetTypeLabel = QtWidgets.QLabel("Ref3 X Offset Type: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef3XOffsetTypeSel = QtWidgets.QComboBox()
        self.pbRef3XOffsetTypeSel.addItem('Absolute')
        self.pbRef3XOffsetTypeSel.addItem('Signed')
        self.pbRef3XOffsetTypeSel.addItem('Absolute Percent')
        self.pbRef3XOffsetTypeSel.addItem('Signed Percent')

        self.pbRef3XOffsetValLabel = QtWidgets.QLabel("Ref3 X Offset Value: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef3XOffsetValEdit = QtWidgets.QLineEdit()
        self.pbRef3XOffsetValEdit.setPlaceholderText("Ex: 1")

        self.pbRef3XOffsetUnitLabel = QtWidgets.QLabel("Ref3 X Offset Unit: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef3XOffsetUnitSel = QtWidgets.QComboBox()
        self.pbRef3XOffsetUnitSel.addItem('Pixel')
        self.pbRef3XOffsetUnitSel.addItem('Letter Height')
        self.pbRef3XOffsetUnitSel.addItem('Image Height')
        self.pbRef3XOffsetUnitSel.addItem('Full Height')
        self.pbRef3XOffsetUnitSel.addItem('Letter Width')
        self.pbRef3XOffsetUnitSel.addItem('Image Width')
        self.pbRef3XOffsetUnitSel.addItem('Full Width')

        self.pbRef3YOffsetDirLabel = QtWidgets.QLabel("Ref3 Y Dir: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef3YOffsetDirSel = QtWidgets.QComboBox()
        self.pbRef3YOffsetDirSel.addItem('Within')
        self.pbRef3YOffsetDirSel.addItem('Beyond')

        self.pbRef3YOffsetTypeLabel = QtWidgets.QLabel("Ref3 Y Offset Type: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef3YOffsetTypeSel = QtWidgets.QComboBox()
        self.pbRef3YOffsetTypeSel.addItem('Absolute')
        self.pbRef3YOffsetTypeSel.addItem('Signed')
        self.pbRef3YOffsetTypeSel.addItem('Absolute Percent')
        self.pbRef3YOffsetTypeSel.addItem('Signed Percent')

        self.pbRef3YOffsetValLabel = QtWidgets.QLabel("Ref3 Y Offset Value: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef3YOffsetValEdit = QtWidgets.QLineEdit()
        self.pbRef3YOffsetValEdit.setPlaceholderText("Ex: 1")

        self.pbRef3YOffsetUnitLabel = QtWidgets.QLabel("Ref3 Y Offset Unit: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef3YOffsetUnitSel = QtWidgets.QComboBox()
        self.pbRef3YOffsetUnitSel.addItem('Pixel')
        self.pbRef3YOffsetUnitSel.addItem('Letter Height')
        self.pbRef3YOffsetUnitSel.addItem('Image Height')
        self.pbRef3YOffsetUnitSel.addItem('Full Height')
        self.pbRef3YOffsetUnitSel.addItem('Letter Width')
        self.pbRef3YOffsetUnitSel.addItem('Image Width')
        self.pbRef3YOffsetUnitSel.addItem('Full Width')

        #  ----------  reference 4 widgets ----------------------------
        self.pbRef4NameLabel = QtWidgets.QLabel("Ref4 Name: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef4NameEdit = QtWidgets.QLineEdit()
        self.pbRef4NameEdit.setPlaceholderText("Ex: abc")

        self.pbRef4XOffsetDirLabel = QtWidgets.QLabel("Ref4 X Offset Dir: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef4XOffsetDirSel = QtWidgets.QComboBox()
        self.pbRef4XOffsetDirSel.addItem('Within')
        self.pbRef4XOffsetDirSel.addItem('Beyond')

        self.pbRef4XOffsetTypeLabel = QtWidgets.QLabel("Ref4 X Offset Type: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef4XOffsetTypeSel = QtWidgets.QComboBox()
        self.pbRef4XOffsetTypeSel.addItem('Absolute')
        self.pbRef4XOffsetTypeSel.addItem('Signed')
        self.pbRef4XOffsetTypeSel.addItem('Absolute Percent')
        self.pbRef4XOffsetTypeSel.addItem('Signed Percent')

        self.pbRef4XOffsetValLabel = QtWidgets.QLabel("Ref4 X Offset Value: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef4XOffsetValEdit = QtWidgets.QLineEdit()
        self.pbRef4XOffsetValEdit.setPlaceholderText("Ex: 1")

        self.pbRef4XOffsetUnitLabel = QtWidgets.QLabel("Ref4 X Offset Unit: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef4XOffsetUnitSel = QtWidgets.QComboBox()
        self.pbRef4XOffsetUnitSel.addItem('Pixel')
        self.pbRef4XOffsetUnitSel.addItem('Letter Height')
        self.pbRef4XOffsetUnitSel.addItem('Image Height')
        self.pbRef4XOffsetUnitSel.addItem('Full Height')
        self.pbRef4XOffsetUnitSel.addItem('Letter Width')
        self.pbRef4XOffsetUnitSel.addItem('Image Width')
        self.pbRef4XOffsetUnitSel.addItem('Full Width')

        self.pbRef4YOffsetDirLabel = QtWidgets.QLabel("Ref4 Y Dir: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef4YOffsetDirSel = QtWidgets.QComboBox()
        self.pbRef4YOffsetDirSel.addItem('Within')
        self.pbRef4YOffsetDirSel.addItem('Beyond')

        self.pbRef4YOffsetTypeLabel = QtWidgets.QLabel("Ref4 Y Offset Type: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef4YOffsetTypeSel = QtWidgets.QComboBox()
        self.pbRef4YOffsetTypeSel.addItem('Absolute')
        self.pbRef4YOffsetTypeSel.addItem('Signed')
        self.pbRef4YOffsetTypeSel.addItem('Absolute Percent')
        self.pbRef4YOffsetTypeSel.addItem('Signed Percent')

        self.pbRef4YOffsetValLabel = QtWidgets.QLabel("Ref4 Y Offset Value: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef4YOffsetValEdit = QtWidgets.QLineEdit()
        self.pbRef4YOffsetValEdit.setPlaceholderText("Ex: 1")

        self.pbRef4YOffsetUnitLabel = QtWidgets.QLabel("Ref4 Y Offset Unit: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRef4YOffsetUnitSel = QtWidgets.QComboBox()
        self.pbRef4YOffsetUnitSel.addItem('Pixel')
        self.pbRef4YOffsetUnitSel.addItem('Letter Height')
        self.pbRef4YOffsetUnitSel.addItem('Image Height')
        self.pbRef4YOffsetUnitSel.addItem('Full Height')
        self.pbRef4YOffsetUnitSel.addItem('Letter Width')
        self.pbRef4YOffsetUnitSel.addItem('Image Width')
        self.pbRef4YOffsetUnitSel.addItem('Full Width')

        # end of reference widgets.

        self.pbInfoL0Layout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL0Layout.addWidget(self.pbInfoNameLabel)
        self.pbInfoL0Layout.addWidget(self.pbInfoNameEdit)

        self.pbInfoL1Layout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL1Layout.addWidget(self.pbInfoLabel)
        self.pbInfoL1Layout.addWidget(self.pbInfoSel)

        self.pbInfoL2ALayout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL2ALayout.addWidget(self.pbATLabel)
        self.pbInfoL2ALayout.addWidget(self.pbATSel)

        self.pbInfoL2Layout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL2Layout.addWidget(self.pbRTLabel)
        self.pbInfoL2Layout.addWidget(self.pbRTSel)

        self.pbInfoL2BLayout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL2BLayout.addWidget(self.pbNRefLabel)
        self.pbInfoL2BLayout.addWidget(self.pbNRefSel)

        self.pbInfoL3Layout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL3Layout.addWidget(self.pbDTLabel)
        self.pbInfoL3Layout.addWidget(self.pbDTSel)

        self.pbInfoL4Layout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL4Layout.addWidget(self.pbNLabel)            #number of line/words
        self.pbInfoL4Layout.addWidget(self.pbNEdit)

        # ref 1
        self.pbInfoL5Layout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL5Layout.addWidget(self.pbRef1NameLabel)
        self.pbInfoL5Layout.addWidget(self.pbRef1NameEdit)

        self.pbInfoL6Layout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL6Layout.addWidget(self.pbRef1XOffsetDirLabel)
        self.pbInfoL6Layout.addWidget(self.pbRef1XOffsetDirSel)

        self.pbInfoL6ALayout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL6ALayout.addWidget(self.pbRef1XOffsetTypeLabel)
        self.pbInfoL6ALayout.addWidget(self.pbRef1XOffsetTypeSel)

        self.pbInfoL6BLayout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL6BLayout.addWidget(self.pbRef1XOffsetValLabel)
        self.pbInfoL6BLayout.addWidget(self.pbRef1XOffsetValEdit)

        self.pbInfoL6CLayout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL6CLayout.addWidget(self.pbRef1XOffsetUnitLabel)
        self.pbInfoL6CLayout.addWidget(self.pbRef1XOffsetUnitSel)

        self.pbInfoL7Layout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL7Layout.addWidget(self.pbRef1YOffsetDirLabel)
        self.pbInfoL7Layout.addWidget(self.pbRef1YOffsetDirSel)

        self.pbInfoL7ALayout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL7ALayout.addWidget(self.pbRef1YOffsetTypeLabel)
        self.pbInfoL7ALayout.addWidget(self.pbRef1YOffsetTypeSel)

        self.pbInfoL7BLayout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL7BLayout.addWidget(self.pbRef1YOffsetValLabel)
        self.pbInfoL7BLayout.addWidget(self.pbRef1YOffsetValEdit)

        self.pbInfoL7CLayout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL7CLayout.addWidget(self.pbRef1YOffsetUnitLabel)
        self.pbInfoL7CLayout.addWidget(self.pbRef1YOffsetUnitSel)
        # ref 2
        self.pbInfoL8Layout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL8Layout.addWidget(self.pbRef2NameLabel)
        self.pbInfoL8Layout.addWidget(self.pbRef2NameEdit)

        self.pbInfoL9Layout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL9Layout.addWidget(self.pbRef2XOffsetDirLabel)
        self.pbInfoL9Layout.addWidget(self.pbRef2XOffsetDirSel)

        self.pbInfoL9ALayout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL9ALayout.addWidget(self.pbRef2XOffsetTypeLabel)
        self.pbInfoL9ALayout.addWidget(self.pbRef2XOffsetTypeSel)

        self.pbInfoL9BLayout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL9BLayout.addWidget(self.pbRef2XOffsetValLabel)
        self.pbInfoL9BLayout.addWidget(self.pbRef2XOffsetValEdit)

        self.pbInfoL9CLayout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL9CLayout.addWidget(self.pbRef2XOffsetUnitLabel)
        self.pbInfoL9CLayout.addWidget(self.pbRef2XOffsetUnitSel)

        self.pbInfoL10Layout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL10Layout.addWidget(self.pbRef2YOffsetDirLabel)
        self.pbInfoL10Layout.addWidget(self.pbRef2YOffsetDirSel)

        self.pbInfoL10ALayout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL10ALayout.addWidget(self.pbRef2YOffsetTypeLabel)
        self.pbInfoL10ALayout.addWidget(self.pbRef2YOffsetTypeSel)

        self.pbInfoL10BLayout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL10BLayout.addWidget(self.pbRef2YOffsetValLabel)
        self.pbInfoL10BLayout.addWidget(self.pbRef2YOffsetValEdit)

        self.pbInfoL10CLayout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL10CLayout.addWidget(self.pbRef2YOffsetUnitLabel)
        self.pbInfoL10CLayout.addWidget(self.pbRef2YOffsetUnitSel)
        # ref 3
        self.pbInfoL11Layout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL11Layout.addWidget(self.pbRef3NameLabel)
        self.pbInfoL11Layout.addWidget(self.pbRef3NameEdit)

        self.pbInfoL12Layout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL12Layout.addWidget(self.pbRef3XOffsetDirLabel)
        self.pbInfoL12Layout.addWidget(self.pbRef3XOffsetDirSel)

        self.pbInfoL12ALayout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL12ALayout.addWidget(self.pbRef3XOffsetTypeLabel)
        self.pbInfoL12ALayout.addWidget(self.pbRef3XOffsetTypeSel)

        self.pbInfoL12BLayout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL12BLayout.addWidget(self.pbRef3XOffsetValLabel)
        self.pbInfoL12BLayout.addWidget(self.pbRef3XOffsetValEdit)

        self.pbInfoL12CLayout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL12CLayout.addWidget(self.pbRef3XOffsetUnitLabel)
        self.pbInfoL12CLayout.addWidget(self.pbRef3XOffsetUnitSel)

        self.pbInfoL13Layout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL13Layout.addWidget(self.pbRef3YOffsetDirLabel)
        self.pbInfoL13Layout.addWidget(self.pbRef3YOffsetDirSel)

        self.pbInfoL13ALayout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL13ALayout.addWidget(self.pbRef3YOffsetTypeLabel)
        self.pbInfoL13ALayout.addWidget(self.pbRef3YOffsetTypeSel)

        self.pbInfoL13BLayout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL13BLayout.addWidget(self.pbRef3YOffsetValLabel)
        self.pbInfoL13BLayout.addWidget(self.pbRef3YOffsetValEdit)

        self.pbInfoL13CLayout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL13CLayout.addWidget(self.pbRef3YOffsetUnitLabel)
        self.pbInfoL13CLayout.addWidget(self.pbRef3YOffsetUnitSel)
        # ref 4
        self.pbInfoL14Layout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL14Layout.addWidget(self.pbRef4NameLabel)
        self.pbInfoL14Layout.addWidget(self.pbRef4NameEdit)

        self.pbInfoL15Layout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL15Layout.addWidget(self.pbRef4XOffsetDirLabel)
        self.pbInfoL15Layout.addWidget(self.pbRef4XOffsetDirSel)

        self.pbInfoL15ALayout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL15ALayout.addWidget(self.pbRef4XOffsetTypeLabel)
        self.pbInfoL15ALayout.addWidget(self.pbRef4XOffsetTypeSel)

        self.pbInfoL15BLayout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL15BLayout.addWidget(self.pbRef4XOffsetValLabel)
        self.pbInfoL15BLayout.addWidget(self.pbRef4XOffsetValEdit)

        self.pbInfoL15CLayout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL15CLayout.addWidget(self.pbRef4XOffsetUnitLabel)
        self.pbInfoL15CLayout.addWidget(self.pbRef4XOffsetUnitSel)

        self.pbInfoL16Layout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL16Layout.addWidget(self.pbRef4YOffsetDirLabel)
        self.pbInfoL16Layout.addWidget(self.pbRef4YOffsetDirSel)

        self.pbInfoL16ALayout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL16ALayout.addWidget(self.pbRef4YOffsetTypeLabel)
        self.pbInfoL16ALayout.addWidget(self.pbRef4YOffsetTypeSel)

        self.pbInfoL16BLayout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL16BLayout.addWidget(self.pbRef4YOffsetValLabel)
        self.pbInfoL16BLayout.addWidget(self.pbRef4YOffsetValEdit)

        self.pbInfoL16CLayout = QtWidgets.QHBoxLayout(self)
        self.pbInfoL16CLayout.addWidget(self.pbRef4YOffsetUnitLabel)
        self.pbInfoL16CLayout.addWidget(self.pbRef4YOffsetUnitSel)
        # end of anchor/user info references
        self.pbInfoLayout.addLayout(self.pbInfoL0Layout)
        self.pbInfoLayout.addLayout(self.pbInfoL1Layout)
        self.pbInfoLayout.addLayout(self.pbInfoL2ALayout)
        self.pbInfoLayout.addLayout(self.pbInfoL2Layout)
        self.pbInfoLayout.addLayout(self.pbInfoL2BLayout)
        self.pbInfoLayout.addLayout(self.pbInfoL3Layout)
        self.pbInfoLayout.addLayout(self.pbInfoL4Layout)
        self.pbInfoLayout.addLayout(self.pbInfoL5Layout)
        self.pbInfoLayout.addLayout(self.pbInfoL6Layout)
        self.pbInfoLayout.addLayout(self.pbInfoL6ALayout)
        self.pbInfoLayout.addLayout(self.pbInfoL6BLayout)
        self.pbInfoLayout.addLayout(self.pbInfoL6CLayout)
        self.pbInfoLayout.addLayout(self.pbInfoL7Layout)
        self.pbInfoLayout.addLayout(self.pbInfoL7ALayout)
        self.pbInfoLayout.addLayout(self.pbInfoL7BLayout)
        self.pbInfoLayout.addLayout(self.pbInfoL7CLayout)
        self.pbInfoLayout.addLayout(self.pbInfoL8Layout)
        self.pbInfoLayout.addLayout(self.pbInfoL9Layout)
        self.pbInfoLayout.addLayout(self.pbInfoL9ALayout)
        self.pbInfoLayout.addLayout(self.pbInfoL9BLayout)
        self.pbInfoLayout.addLayout(self.pbInfoL9CLayout)
        self.pbInfoLayout.addLayout(self.pbInfoL10Layout)
        self.pbInfoLayout.addLayout(self.pbInfoL10ALayout)
        self.pbInfoLayout.addLayout(self.pbInfoL10BLayout)
        self.pbInfoLayout.addLayout(self.pbInfoL10CLayout)
        self.pbInfoLayout.addLayout(self.pbInfoL11Layout)
        self.pbInfoLayout.addLayout(self.pbInfoL12Layout)
        self.pbInfoLayout.addLayout(self.pbInfoL12ALayout)
        self.pbInfoLayout.addLayout(self.pbInfoL12BLayout)
        self.pbInfoLayout.addLayout(self.pbInfoL12CLayout)
        self.pbInfoLayout.addLayout(self.pbInfoL13Layout)
        self.pbInfoLayout.addLayout(self.pbInfoL13ALayout)
        self.pbInfoLayout.addLayout(self.pbInfoL13BLayout)
        self.pbInfoLayout.addLayout(self.pbInfoL13CLayout)
        self.pbInfoLayout.addLayout(self.pbInfoL14Layout)
        self.pbInfoLayout.addLayout(self.pbInfoL15Layout)
        self.pbInfoLayout.addLayout(self.pbInfoL15ALayout)
        self.pbInfoLayout.addLayout(self.pbInfoL15BLayout)
        self.pbInfoLayout.addLayout(self.pbInfoL15CLayout)
        self.pbInfoLayout.addLayout(self.pbInfoL16Layout)
        self.pbInfoLayout.addLayout(self.pbInfoL16ALayout)
        self.pbInfoLayout.addLayout(self.pbInfoL16BLayout)
        self.pbInfoLayout.addLayout(self.pbInfoL16CLayout)


        self.IA_Add_button = QtWidgets.QPushButton("Add")
        self.IA_Remove_button = QtWidgets.QPushButton("Remove")
        self.IA_Save_button = QtWidgets.QPushButton("Save")
        self.pbskButtonsLayout = QtWidgets.QHBoxLayout(self)
        self.pbskButtonsLayout.addWidget(self.IA_Remove_button)
        self.pbskButtonsLayout.addWidget(self.IA_Add_button)
        self.pbskButtonsLayout.addWidget(self.IA_Save_button)

        # self.pbskAnchorListView = QtWidgets.QListView()
        self.pbskAnchorListView = AnchorListView()
        self.pbskAnchorListView.installEventFilter(self)
        self.anchorListModel = QtGui.QStandardItemModel(self.pbskAnchorListView)
        self.pbskAnchorListView.setModel(self.anchorListModel)
        self.pbskAnchorListView.setViewMode(QtWidgets.QListView.IconMode)
        self.pbskAnchorListView.setMovement(QtWidgets.QListView.Snap)
        # newach = ANCHOR("abc", "image")
        # self.anchorListModel.appendRow(newach)

        self.pbskDataListView = QtWidgets.QListView()
        self.pbskDataListView.installEventFilter(self)
        self.dataListModel = QtGui.QStandardItemModel(self.pbskDataListView)
        self.pbskDataListView.setModel(self.dataListModel)
        self.pbskDataListView.setViewMode(QtWidgets.QListView.ListMode)
        self.pbskDataListView.setMovement(QtWidgets.QListView.Snap)
        # newui = USER_INFO("aaa")
        # self.dataListModel.appendRow(newui)

        self.pbskStepListView = QtWidgets.QListView()
        self.pbskStepListView.installEventFilter(self)
        self.stepListModel = QtGui.QStandardItemModel(self.pbskStepListView)
        self.pbskStepListView.setModel(self.stepListModel)
        self.pbskStepListView.setViewMode(QtWidgets.QListView.ListMode)
        self.pbskStepListView.setMovement(QtWidgets.QListView.Snap)
        # newst = PROCEDURAL_STEP("bbb")
        # self.stepListModel.appendRow(newst)


        self.pbInfoWidget.setLayout(self.pbInfoLayout)

        self.pbInfoArea = QtWidgets.QScrollArea()
        self.pbInfoArea.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.pbInfoArea.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.pbInfoArea.setWidget(self.pbInfoWidget)

        self.pbStepNameLabel = QtWidgets.QLabel("Step Name: ", alignment=QtCore.Qt.AlignLeft)
        self.pbStepNameEdit = QtWidgets.QLineEdit()
        self.pbStepNameEdit.setPlaceholderText("Ex: Step1")
        self.pbActionL0Layout = QtWidgets.QHBoxLayout(self)
        self.pbActionL0Layout.addWidget(self.pbStepNameLabel)
        self.pbActionL0Layout.addWidget(self.pbStepNameEdit)

        self.pbStepNumberLabel = QtWidgets.QLabel("Step #: ", alignment=QtCore.Qt.AlignLeft)
        self.pbStepNumberEdit = QtWidgets.QLineEdit()
        self.pbStepNumberEdit.setPlaceholderText("Ex: 1")
        self.pbActionL0ALayout = QtWidgets.QHBoxLayout(self)
        self.pbActionL0ALayout.addWidget(self.pbStepNumberLabel)
        self.pbActionL0ALayout.addWidget(self.pbStepNumberEdit)

        self.pbStepPrevNextLabel = QtWidgets.QLabel("Located ", alignment=QtCore.Qt.AlignLeft)
        self.pbStepPrevNextSel = QtWidgets.QComboBox()
        self.pbStepPrevNextSel.addItem('After')
        self.pbStepPrevNextSel.addItem('Before')
        self.pbActionL0BLayout = QtWidgets.QHBoxLayout(self)
        self.pbActionL0BLayout.addWidget(self.pbStepPrevNextLabel)
        self.pbActionL0BLayout.addWidget(self.pbStepPrevNextSel)
        self.pbStepPrevNextSel.currentTextChanged.connect(self.pbStepPrevNextSel_changed)


        self.pbStepPrevNextNameLabel = QtWidgets.QLabel("Prev. Step Name: ", alignment=QtCore.Qt.AlignLeft)
        self.pbStepPrevNextNameEdit = QtWidgets.QLineEdit()
        self.stepNameCompleter = QtWidgets.QCompleter(self.step_names)
        self.pbStepPrevNextNameEdit.setCompleter(self.stepNameCompleter)
        self.pbStepPrevNextNameEdit.setPlaceholderText("Ex: step1")
        self.pbActionL0CLayout = QtWidgets.QHBoxLayout(self)
        self.pbActionL0CLayout.addWidget(self.pbStepPrevNextNameLabel)
        self.pbActionL0CLayout.addWidget(self.pbStepPrevNextNameEdit)

        self.pbActionLabel = QtWidgets.QLabel("Action: ", alignment=QtCore.Qt.AlignLeft)
        self.pbActionSel = QtWidgets.QComboBox()
        self.pbActionSel.addItem('App Page Open')
        self.pbActionSel.addItem('Browse')
        self.pbActionSel.addItem('Create Data')
        self.pbActionSel.addItem('Mouse Action')
        self.pbActionSel.addItem('Keyboard Action')
        self.pbActionSel.addItem('Load Data')
        self.pbActionSel.addItem('Save Data')
        self.pbActionSel.addItem('Conditional Step')
        self.pbActionSel.addItem('Jump Step')
        self.pbActionSel.addItem('Run Routine')
        self.pbActionSel.addItem('Set Wait')
        self.pbActionSel.addItem('Halt')
        self.pbActionSel.addItem('Run Routine')
        self.pbActionSel.addItem('Run Extern')
        self.pbActionSel.currentTextChanged.connect(self.pbActionSel_changed)

        self.pbActionL1Layout = QtWidgets.QHBoxLayout(self)
        self.pbActionL1Layout.addWidget(self.pbActionLabel)
        self.pbActionL1Layout.addWidget(self.pbActionSel)

        self.pbAppLinkLabel = QtWidgets.QLabel("App Exe: ", alignment=QtCore.Qt.AlignLeft)
        self.pbAppLinkEdit = QtWidgets.QLineEdit()
        self.pbAppLinkEdit.setPlaceholderText("Full Path To .exe")
        self.pbActionL2Layout = QtWidgets.QHBoxLayout(self)
        self.pbActionL2Layout.addWidget(self.pbAppLinkLabel)
        self.pbActionL2Layout.addWidget(self.pbAppLinkEdit)

        self.pbPageURLLabel = QtWidgets.QLabel("Page URL: ", alignment=QtCore.Qt.AlignLeft)
        self.pbPageURLEdit = QtWidgets.QLineEdit()
        self.pbPageURLEdit.setPlaceholderText("full url")
        self.pbActionL3Layout = QtWidgets.QHBoxLayout(self)
        self.pbActionL3Layout.addWidget(self.pbPageURLLabel)
        self.pbActionL3Layout.addWidget(self.pbPageURLEdit)

        self.pbDataNameLabel = QtWidgets.QLabel("Data Name: ", alignment=QtCore.Qt.AlignLeft)
        self.pbDataNameEdit = QtWidgets.QLineEdit()
        self.pbDataNameEdit.setPlaceholderText("ex: abc")
        self.pbActionL4Layout = QtWidgets.QHBoxLayout(self)
        self.pbActionL4Layout.addWidget(self.pbDataNameLabel)
        self.pbActionL4Layout.addWidget(self.pbDataNameEdit)

        self.pbMouseActionLabel = QtWidgets.QLabel("Mouse Action: ", alignment=QtCore.Qt.AlignLeft)
        self.pbMouseActionSel = QtWidgets.QComboBox()
        self.pbMouseActionSel.addItem('Single Click')
        self.pbMouseActionSel.addItem('Double Click')
        self.pbMouseActionSel.addItem('Right Click')
        self.pbMouseActionSel.addItem('Scroll Up')
        self.pbMouseActionSel.addItem('Scroll Down')
        self.pbActionL5Layout = QtWidgets.QHBoxLayout(self)
        self.pbActionL5Layout.addWidget(self.pbMouseActionLabel)
        self.pbActionL5Layout.addWidget(self.pbMouseActionSel)

        self.pbMouseActionAmountLabel = QtWidgets.QLabel("Scroll Amount: ", alignment=QtCore.Qt.AlignLeft)
        self.pbMouseActionAmountEdit = QtWidgets.QLineEdit()
        self.pbMouseActionAmountEdit.setPlaceholderText("ex: 4")
        self.pbActionL6Layout = QtWidgets.QHBoxLayout(self)
        self.pbActionL6Layout.addWidget(self.pbMouseActionAmountLabel)
        self.pbActionL6Layout.addWidget(self.pbMouseActionAmountEdit)

        self.pbKeyboardActionLabel = QtWidgets.QLabel("String To Input: ", alignment=QtCore.Qt.AlignLeft)
        self.pbKeyboardActionEdit = QtWidgets.QLineEdit()
        self.pbKeyboardActionEdit.setPlaceholderText("ex: abc")
        self.pbActionL7Layout = QtWidgets.QHBoxLayout(self)
        self.pbActionL7Layout.addWidget(self.pbKeyboardActionLabel)
        self.pbActionL7Layout.addWidget(self.pbKeyboardActionEdit)

        self.pbDataFileLabel = QtWidgets.QLabel("File Name: ", alignment=QtCore.Qt.AlignLeft)
        self.pbDataFileEdit = QtWidgets.QLineEdit()
        self.pbDataFileEdit.setPlaceholderText("full path to data file")
        self.pbActionL8Layout = QtWidgets.QHBoxLayout(self)
        self.pbActionL8Layout.addWidget(self.pbDataFileLabel)
        self.pbActionL8Layout.addWidget(self.pbDataFileEdit)

        self.pbConditionLabel = QtWidgets.QLabel("Condition Expression: ", alignment=QtCore.Qt.AlignLeft)
        self.pbConditionEdit = QtWidgets.QLineEdit()
        self.pbConditionEdit.setPlaceholderText("example: a > 5")
        self.pbActionL9Layout = QtWidgets.QHBoxLayout(self)
        self.pbActionL9Layout.addWidget(self.pbConditionLabel)
        self.pbActionL9Layout.addWidget(self.pbConditionEdit)

        self.pbConditionTrueLabel = QtWidgets.QLabel("If True: ", alignment=QtCore.Qt.AlignLeft)
        self.pbConditionTrueEdit = QtWidgets.QLineEdit()
        self.pbConditionTrueEdit.setPlaceholderText("step name here")
        self.pbActionL10Layout = QtWidgets.QHBoxLayout(self)
        self.pbActionL10Layout.addWidget(self.pbConditionTrueLabel)
        self.pbActionL10Layout.addWidget(self.pbConditionTrueEdit)

        self.pbConditionFalseLabel = QtWidgets.QLabel("If False: ", alignment=QtCore.Qt.AlignLeft)
        self.pbConditionFalseEdit = QtWidgets.QLineEdit()
        self.pbConditionFalseEdit.setPlaceholderText("step name here")
        self.pbActionL11Layout = QtWidgets.QHBoxLayout(self)
        self.pbActionL11Layout.addWidget(self.pbConditionFalseLabel)
        self.pbActionL11Layout.addWidget(self.pbConditionFalseEdit)

        self.pbJumpLabel = QtWidgets.QLabel("Jump to: ", alignment=QtCore.Qt.AlignLeft)
        self.pbJumpEdit = QtWidgets.QLineEdit()
        self.pbJumpEdit.setPlaceholderText("step name here")
        self.pbActionL12Layout = QtWidgets.QHBoxLayout(self)
        self.pbActionL12Layout.addWidget(self.pbJumpLabel)
        self.pbActionL12Layout.addWidget(self.pbJumpEdit)

        self.pbRoutineLabel = QtWidgets.QLabel("Subroutine Name: ", alignment=QtCore.Qt.AlignLeft)
        self.pbRoutineEdit = QtWidgets.QLineEdit()
        self.pbRoutineEdit.setPlaceholderText("subroutine name here")
        self.pbActionL13Layout = QtWidgets.QHBoxLayout(self)
        self.pbActionL13Layout.addWidget(self.pbRoutineLabel)
        self.pbActionL13Layout.addWidget(self.pbRoutineEdit)

        self.pbExternLabel = QtWidgets.QLabel("External Script: ", alignment=QtCore.Qt.AlignLeft)
        self.pbExternEdit = QtWidgets.QLineEdit()
        self.pbExternEdit.setPlaceholderText("extern script name here")
        self.pbActionL14Layout = QtWidgets.QHBoxLayout(self)
        self.pbActionL14Layout.addWidget(self.pbExternLabel)
        self.pbActionL14Layout.addWidget(self.pbExternEdit)

        self.pbWaittimeLabel = QtWidgets.QLabel("Wait Time: ", alignment=QtCore.Qt.AlignLeft)
        self.pbWaittimeEdit = QtWidgets.QLineEdit()
        self.pbWaittimeEdit.setPlaceholderText("time in seconds.")
        self.pbActionL15Layout = QtWidgets.QHBoxLayout(self)
        self.pbActionL15Layout.addWidget(self.pbWaittimeLabel)
        self.pbActionL15Layout.addWidget(self.pbWaittimeEdit)

        self.pbActionWidget = QtWidgets.QWidget()
        self.pbActionLayout = QtWidgets.QVBoxLayout(self)
        self.pbActionLayout.setAlignment(Qt.AlignTop)

        self.pbActionLayout.addLayout(self.pbActionL0Layout)
        self.pbActionLayout.addLayout(self.pbActionL0ALayout)
        self.pbActionLayout.addLayout(self.pbActionL0BLayout)
        self.pbActionLayout.addLayout(self.pbActionL0CLayout)

        self.pbActionLayout.addLayout(self.pbActionL2Layout)
        self.pbActionLayout.addLayout(self.pbActionL3Layout)
        self.pbActionLayout.addLayout(self.pbActionL4Layout)
        self.pbActionLayout.addLayout(self.pbActionL5Layout)
        self.pbActionLayout.addLayout(self.pbActionL6Layout)
        self.pbActionLayout.addLayout(self.pbActionL7Layout)
        self.pbActionLayout.addLayout(self.pbActionL8Layout)
        self.pbActionLayout.addLayout(self.pbActionL9Layout)
        self.pbActionLayout.addLayout(self.pbActionL10Layout)
        self.pbActionLayout.addLayout(self.pbActionL11Layout)
        self.pbActionLayout.addLayout(self.pbActionL12Layout)
        self.pbActionLayout.addLayout(self.pbActionL13Layout)
        self.pbActionLayout.addLayout(self.pbActionL14Layout)
        self.pbActionLayout.addLayout(self.pbActionL15Layout)

        self.pbActionWidget.setLayout(self.pbActionLayout)

        self.pbActionArea = QtWidgets.QScrollArea()
        self.pbActionArea.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.pbActionArea.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.pbActionArea.setWidget(self.pbActionWidget)

        self.skvtabs = QtWidgets.QTabWidget()
        self.skconsolelabel = QtWidgets.QLabel("Console", alignment=QtCore.Qt.AlignLeft)
        self.skconsole = QtWidgets.QTextBrowser()
        self.skcodeeditor = PMGPythonEditor()

        self.skill_load_button = QtWidgets.QPushButton("Load Skill")
        self.skill_save_button = QtWidgets.QPushButton("Save Skill")
        self.skill_cancel_button = QtWidgets.QPushButton("Cancel")
        self.skill_run_button = QtWidgets.QPushButton("Trial Run")
        self.skill_step_button = QtWidgets.QPushButton("Step")
        self.skill_stop_button = QtWidgets.QPushButton("Stop")
        self.skill_resume_button = QtWidgets.QPushButton("Continue")

        self.skFCWidget = QtWidgets.QScrollArea()
        self.skFCWidget.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.skFCWidget.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)

        self.skCodeWidget = QtWidgets.QScrollArea()
        self.skCodeWidget.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.skCodeWidget.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)

        self.skFCDiagram = PyQDiagram()
        # ------- layouts ------------
        self.pbbuttonlayout = QtWidgets.QHBoxLayout(self)
        self.pbrunlayout = QtWidgets.QVBoxLayout(self)
        self.pblayout = QtWidgets.QHBoxLayout(self)
        self.pbsklayout = QtWidgets.QVBoxLayout(self)

        self.skblayout = QtWidgets.QHBoxLayout(self)

        self.sklayout = QtWidgets.QVBoxLayout(self)

        # ---- populate layout --------
        self.pbbuttonlayout.addWidget(self.playback_start_button)
        self.pbbuttonlayout.addWidget(self.playback_next_button)
        self.pbbuttonlayout.addWidget(self.playback_back_button)
        self.pbbuttonlayout.addWidget(self.playback_reload_button)

        self.pbrunlayout.addLayout(self.pbbuttonlayout)
        self.pbrunlayout.addWidget(self.pbview)
        self.pbrunWidget = QtWidgets.QWidget()
        self.pbrunWidget.setLayout(self.pbrunlayout)

        self.pbtabs.addTab(self.pbInfoArea, "Feature Info")
        self.pbtabs.addTab(self.pbActionArea, "Step")

        self.pbskAppLabel = QtWidgets.QLabel("App: ", alignment=QtCore.Qt.AlignLeft)
        self.pbskDomainLabel = QtWidgets.QLabel("Domain: ", alignment=QtCore.Qt.AlignLeft)
        self.pbskPageLabel = QtWidgets.QLabel("Page: ", alignment=QtCore.Qt.AlignLeft)
        self.pbskSkillLabel = QtWidgets.QLabel("Skill: ", alignment=QtCore.Qt.AlignLeft)
        self.pbskAppEdit = QtWidgets.QLineEdit()
        self.pbskAppEdit.setPlaceholderText("type in App name here")
        self.pbskAppEdit.textChanged.connect(self.appDomainPage_changed)
        self.pbskDomainEdit = QtWidgets.QLineEdit()
        self.pbskDomainEdit.setPlaceholderText("type in Domain name here")
        self.pbskDomainEdit.textChanged.connect(self.appDomainPage_changed)
        self.pbskPageEdit = QtWidgets.QLineEdit()
        self.pbskPageEdit.setPlaceholderText("type in page name here")
        self.pbskPageEdit.textChanged.connect(self.appDomainPage_changed)
        self.pbskSkillEdit = QtWidgets.QLineEdit()
        self.pbskSkillEdit.setPlaceholderText("type in skill name here")
        self.pbskSkillEdit.textChanged.connect(self.appDomainPage_changed)

        self.pbskl1Layout = QtWidgets.QHBoxLayout(self)
        self.pbskl1Layout.addWidget(self.pbskAppLabel)
        self.pbskl1Layout.addWidget(self.pbskAppEdit)
        self.pbskl1ALayout = QtWidgets.QHBoxLayout(self)
        self.pbskl1ALayout.addWidget(self.pbskDomainLabel)
        self.pbskl1ALayout.addWidget(self.pbskDomainEdit)
        self.pbskl2Layout = QtWidgets.QHBoxLayout(self)
        self.pbskl2Layout.addWidget(self.pbskPageLabel)
        self.pbskl2Layout.addWidget(self.pbskPageEdit)
        self.pbskl3Layout = QtWidgets.QHBoxLayout(self)
        self.pbskl3Layout.addWidget(self.pbskSkillLabel)
        self.pbskl3Layout.addWidget(self.pbskSkillEdit)

        self.pbskALLabel = QtWidgets.QLabel("Anchor List:")
        self.pbskALWidget = QtWidgets.QWidget()
        self.pbskALLayout = QtWidgets.QVBoxLayout(self)
        self.pbskALLayout.addWidget(self.pbskALLabel)

        self.pbskAnchorListScroll = QtWidgets.QScrollArea()
        self.pbskAnchorListScroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.pbskAnchorListScroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.pbskAnchorListScroll.setWidget(self.pbskAnchorListView)

        self.pbskALLayout.addWidget(self.pbskAnchorListScroll)
        self.pbskALWidget.setLayout(self.pbskALLayout)

        self.pbskDLLabel = QtWidgets.QLabel("Useful Data List:")
        self.pbskDLWidget = QtWidgets.QWidget()
        self.pbskDLLayout = QtWidgets.QVBoxLayout(self)
        self.pbskDLLayout.addWidget(self.pbskDLLabel)


        self.pbskDataListScroll = QtWidgets.QScrollArea()
        self.pbskDataListScroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.pbskDataListScroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.pbskDataListScroll.setWidget(self.pbskDataListView)

        self.pbskDLLayout.addWidget(self.pbskDataListScroll)
        self.pbskDLWidget.setLayout(self.pbskDLLayout)


        self.pbskSLLabel = QtWidgets.QLabel("Step List:")
        self.pbskSLWidget = QtWidgets.QWidget()
        self.pbskSLLayout = QtWidgets.QVBoxLayout(self)
        self.pbskSLLayout.addWidget(self.pbskSLLabel)

        self.pbskStepListScroll = QtWidgets.QScrollArea()
        self.pbskStepListScroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.pbskStepListScroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.pbskStepListScroll.setWidget(self.pbskStepListView)

        self.pbskSLLayout.addWidget(self.pbskStepListScroll)
        self.pbskSLWidget.setLayout(self.pbskSLLayout)

        self.pbskButtonsWidget = QtWidgets.QWidget()
        self.pbskButtonsWidget.setLayout(self.pbskButtonsLayout)
        self.hsplitter2.addWidget(self.pbtabs)
        self.hsplitter2.addWidget(self.pbskALWidget)
        self.hsplitter2.addWidget(self.pbskDLWidget)
        self.hsplitter2.addWidget(self.pbskSLWidget)
        self.pbskSLWidget.setVisible(False)
        self.hsplitter2.addWidget(self.pbskButtonsWidget)

        self.pbsklayout.addLayout(self.pbskl1Layout)
        self.pbsklayout.addLayout(self.pbskl1ALayout)
        self.pbsklayout.addLayout(self.pbskl2Layout)
        self.pbsklayout.addLayout(self.pbskl3Layout)
        self.pbsklayout.addLayout(self.pbActionL1Layout)
        self.pbsklayout.addWidget(self.hsplitter2)



        self.pbskWidget = QtWidgets.QWidget()
        self.pbskWidget.setLayout(self.pbsklayout)

        self.skblayout.addWidget(self.skill_load_button)
        self.skblayout.addWidget(self.skill_run_button)
        self.skblayout.addWidget(self.skill_step_button)
        self.skblayout.addWidget(self.skill_save_button)
        self.skblayout.addWidget(self.skill_cancel_button)

        self.skCodeWidget.setWidget(self.skcodeeditor)
        self.skCodeWidget.setWidgetResizable(True)
        self.skFCWidget.setWidget(self.skFCDiagram)

        self.skvtabs.addTab(self.skFCDiagram.widget, "Flow Chart")
        self.skvtabs.addTab(self.skCodeWidget, "Code")


        self.hsplitter1.addWidget(self.skvtabs)
        self.consoleWidget = QtWidgets.QWidget()
        self.consoleLayout = QtWidgets.QVBoxLayout(self)
        self.consoleLayout.addWidget(self.skconsolelabel)
        self.consoleLayout.addWidget(self.skconsole)
        self.consoleWidget.setLayout(self.consoleLayout)
        self.hsplitter1.addWidget(self.consoleWidget)

        self.sklayout.addWidget(self.hsplitter1)
        self.sklayout.addLayout(self.skblayout)

        self.layout = QtWidgets.QHBoxLayout(self)


        self.skWidget = QtWidgets.QWidget()
        self.skWidget.setLayout(self.sklayout)

        self.vsplitter1.addWidget(self.pbrunWidget)
        self.vsplitter1.addWidget(self.pbskWidget)
        self.vsplitter1.addWidget(self.skWidget)
        self.vsplitter1.setStretchFactor(1, 1)
        self.vsplitter1.setChildrenCollapsible(0)
        self.vsplitter1.setChildrenCollapsible(1)

        self.pbtabs.currentChanged.connect(self.IndividualItemChanged)

        #self.layout.addLayout(self.pblayout)
        #self.layout.addLayout(self.sklayout)
        self.layout.addWidget(self.vsplitter1)

        self.mainWidget.setLayout(self.layout)
        self.setCentralWidget(self.mainWidget)

        app = QtWidgets.QApplication.instance()
        screen = app.primaryScreen()
        #print('Screen: %s' % screen.name())
        size = screen.size()
        print('Size: %d x %d' % (size.width(), size.height()))

        self.IA_Add_button.clicked.connect(self.ia_add)
        self.IA_Save_button.clicked.connect(self.ia_save)
        self.IA_Remove_button.clicked.connect(self.ia_remove)

        self.skill_load_button.clicked.connect(self.load_skill_file)
        self.skill_save_button.clicked.connect(self.save_skill_file)
        self.skill_cancel_button.clicked.connect(self.cancel_run)
        self.skill_run_button.clicked.connect(self.trial_run)
        self.skill_step_button.clicked.connect(self.run_step)
        self.skill_stop_button.clicked.connect(self.stop_run)
        self.skill_resume_button.clicked.connect(self.continue_run)

        # self.pbview.rubberBandChanged.connect(self.select_contents)
        # self.pbscene.selectionChanged.connect(self.select_contents)

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
        if self.pbActionSel.currentText() == 'App Page Open':
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
        elif self.pbActionSel.currentText() == 'Create Data':
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
        elif self.pbActionSel.currentText() == 'Browse':
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
        elif self.pbActionSel.currentText() == 'Mouse Action':
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
        elif self.pbActionSel.currentText() == 'Keyboard Action':
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
        elif self.pbActionSel.currentText() == 'Load Data':
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
        elif self.pbActionSel.currentText() == 'Save Data':
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
        elif self.pbActionSel.currentText() == 'Conditional Step':
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
        elif self.pbActionSel.currentText() == 'Jump Step':
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
        elif self.pbActionSel.currentText() == 'Set Wait':
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
        elif self.pbActionSel.currentText() == 'Run Routine':
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
        elif self.pbActionSel.currentText() == 'Run External':
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
        file_name = "C:/Users/Teco/PycharmProjects/ecbot/resource/songc_yahoo/win/chrome_amz_main/temp/step1.png"
        self.req_train(file_name)

    def train_next_step(self):
        self.step_count = self.step_count + 1
        file_name = "C:/Users/Teco/PycharmProjects/ecbot/resource/songc_yahoo/win/chrome_amz_main/temp/step" + str(self.step_count) + ".png"
        print("next step... ", self.step_count)
        self.req_train(file_name)


    def train_prev_step(self):
        self.step_count = self.step_count - 1
        file_name = "C:/Users/Teco/PycharmProjects/ecbot/resource/songc_yahoo/win/amz_main/temp/step" + str(self.step_count) + ".png"
        print("prev step... ", self.step_count)
        self.req_train(file_name)
    def re_train_step(self):
        print("refresh... ", self.step_count)
        file_name = "C:/Users/Teco/PycharmProjects/ecbot/resource/songc_yahoo/win/amz_main/temp/step" + str(self.step_count) + ".png"
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
        result = send_screen(file_name, bucket="winrpa")
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
        new_action.setText("&Set Anchor")
        return new_action

    def _createSetUDAction(self):
       new_action = QtGui.QAction(self)
       new_action.setText("&Set Useful Data")
       return new_action

    def _createClearBBAction(self):
       new_action = QtGui.QAction(self)
       new_action.setText("&Clear Bound Box")
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
                    refx = {"dir": self.pbRef1XOffsetDirSel.currentText(), "type": self.pbRef1XOffsetTypeSel.currentText(),
                            "val": self.pbRef1XOffsetValEdit.text(), "unit": self.pbRef1XOffsetUnitSel.currentText()}
                    refy = {"dir": self.pbRef1YOffsetDirSel.currentText(), "type": self.pbRef1YOffsetTypeSel.currentText(),
                            "val": self.pbRef1YOffsetValEdit.text(), "unit": self.pbRef1YOffsetUnitSel.currentText()}
                    self.newAnchor.add_ref(self.pbRef1NameEdit.text(), refx, refy)
                elif  self.pbNRefSel.currentText == '2':
                    refx = {"dir": self.pbRef1XOffsetDirSel.currentText(), "type": self.pbRef1XOffsetTypeSel.currentText(),
                            "val": self.pbRef1XOffsetValEdit.text(), "unit": self.pbRef1XOffsetUnitSel.currentText()}
                    refy = {"dir": self.pbRef1YOffsetDirSel.currentText(), "type": self.pbRef1YOffsetTypeSel.currentText(),
                            "val": self.pbRef1YOffsetValEdit.text(), "unit": self.pbRef1YOffsetUnitSel.currentText()}
                    self.newAnchor.add_ref(self.pbRef1NameEdit.text(), refx, refy)
                    refx = {"dir": self.pbRef2XOffsetDirSel.currentText(), "type": self.pbRef2XOffsetTypeSel.currentText(),
                            "val": self.pbRef2XOffsetValEdit.text(), "unit": self.pbRef2XOffsetUnitSel.currentText()}
                    refy = {"dir": self.pbRef2YOffsetDirSel.currentText(), "type": self.pbRef2YOffsetTypeSel.currentText(),
                            "val": self.pbRef2YOffsetValEdit.text(), "unit": self.pbRef2YOffsetUnitSel.currentText()}
                    self.newAnchor.add_ref(self.pbRef2NameEdit.text(), refx, refy)
                elif self.pbNRefSel.currentText == '3':
                    refx = {"dir": self.pbRef1XOffsetDirSel.currentText(), "type": self.pbRef1XOffsetTypeSel.currentText(),
                            "val": self.pbRef1XOffsetValEdit.text(), "unit": self.pbRef1XOffsetUnitSel.currentText()}
                    refy = {"dir": self.pbRef1YOffsetDirSel.currentText(), "type": self.pbRef1YOffsetTypeSel.currentText(),
                            "val": self.pbRef1YOffsetValEdit.text(), "unit": self.pbRef1YOffsetUnitSel.currentText()}
                    self.newAnchor.add_ref(self.pbRef1NameEdit.text(), refx, refy)
                    refx = {"dir": self.pbRef2XOffsetDirSel.currentText(), "type": self.pbRef2XOffsetTypeSel.currentText(),
                            "val": self.pbRef2XOffsetValEdit.text(), "unit": self.pbRef2XOffsetUnitSel.currentText()}
                    refy = {"dir": self.pbRef2YOffsetDirSel.currentText(), "type": self.pbRef2YOffsetTypeSel.currentText(),
                            "val": self.pbRef2YOffsetValEdit.text(), "unit": self.pbRef2YOffsetUnitSel.currentText()}
                    self.newAnchor.add_ref(self.pbRef2NameEdit.text(), refx, refy)
                    refx = {"dir": self.pbRef3XOffsetDirSel.currentText(), "type": self.pbRef3XOffsetTypeSel.currentText(),
                            "val": self.pbRef3XOffsetValEdit.text(), "unit": self.pbRef3XOffsetUnitSel.currentText()}
                    refy = {"dir": self.pbRef3YOffsetDirSel.currentText(), "type": self.pbRef3YOffsetTypeSel.currentText(),
                            "val": self.pbRef3YOffsetValEdit.text(), "unit": self.pbRef3YOffsetUnitSel.currentText()}
                    self.newAnchor.add_ref(self.pbRef3NameEdit.text(), refx, refy)
                elif self.pbNRefSel.currentText == '4':
                    refx = {"dir": self.pbRef1XOffsetDirSel.currentText(), "type": self.pbRef1XOffsetTypeSel.currentText(),
                            "val": self.pbRef1XOffsetValEdit.text(), "unit": self.pbRef1XOffsetUnitSel.currentText()}
                    refy = {"dir": self.pbRef1YOffsetDirSel.currentText(), "type": self.pbRef1YOffsetTypeSel.currentText(),
                            "val": self.pbRef1YOffsetValEdit.text(), "unit": self.pbRef1YOffsetUnitSel.currentText()}
                    self.newAnchor.add_ref(self.pbRef1NameEdit.text(), refx, refy)
                    refx = {"dir": self.pbRef2XOffsetDirSel.currentText(), "type": self.pbRef2XOffsetTypeSel.currentText(),
                            "val": self.pbRef2XOffsetValEdit.text(), "unit": self.pbRef2XOffsetUnitSel.currentText()}
                    refy = {"dir": self.pbRef2YOffsetDirSel.currentText(), "type": self.pbRef2YOffsetTypeSel.currentText(),
                            "val": self.pbRef2YOffsetValEdit.text(), "unit": self.pbRef2YOffsetUnitSel.currentText()}
                    self.newAnchor.add_ref(self.pbRef2NameEdit.text(), refx, refy)
                    refx = {"dir": self.pbRef3XOffsetDirSel.currentText(), "type": self.pbRef3XOffsetTypeSel.currentText(),
                            "val": self.pbRef3XOffsetValEdit.text(), "unit": self.pbRef3XOffsetUnitSel.currentText()}
                    refy = {"dir": self.pbRef3YOffsetDirSel.currentText(), "type": self.pbRef3YOffsetTypeSel.currentText(),
                            "val": self.pbRef3YOffsetValEdit.text(), "unit": self.pbRef3YOffsetUnitSel.currentText()}
                    self.newAnchor.add_ref(self.pbRef3NameEdit.text(), refx, refy)
                    refx = {"dir": self.pbRef4XOffsetDirSel.currentText(), "type": self.pbRef4XOffsetTypeSel.currentText(),
                            "val": self.pbRef4XOffsetValEdit.text(), "unit": self.pbRef4XOffsetUnitSel.currentText()}
                    refy = {"dir": self.pbRef4YOffsetDirSel.currentText(), "type": self.pbRef4YOffsetTypeSel.currentText(),
                            "val": self.pbRef4YOffsetValEdit.text(), "unit": self.pbRef4YOffsetUnitSel.currentText()}
                    self.newAnchor.add_ref(self.pbRef4NameEdit.text(), refx, refy)
                    print("ready to add....")
                self.anchorListModel.appendRow(self.newAnchor)
            elif self.pbInfoSel.currentText() == "Useful Data":
                print("add a new user info....")
                self.newUserInfo = USER_INFO(self.pbInfoNameEdit.text())
                self.newUserInfo.set_type(self.pbDTSel.currentText())
                self.newUserInfo.set_nlines(self.pbNEdit.text())
                self.newUserInfo.set_ref_method(self.pbRTSel.currentText())
                if self.pbNRefSel.currentText == '1':
                    refx = {"dir": self.pbRef1XOffsetDirSel.currentText(), "type": self.pbRef1XOffsetTypeSel.currentText(),
                            "val": self.pbRef1XOffsetValEdit.text(), "unit": self.pbRef1XOffsetUnitSel.currentText()}
                    refy = {"dir": self.pbRef1YOffsetDirSel.currentText(), "type": self.pbRef1YOffsetTypeSel.currentText(),
                            "val": self.pbRef1YOffsetValEdit.text(), "unit": self.pbRef1YOffsetUnitSel.currentText()}
                    self.newUserInfo.add_ref(self.pbRef1NameEdit.text(), refx, refy)
                elif  self.pbNRefSel.currentText == '2':
                    refx = {"dir": self.pbRef1XOffsetDirSel.currentText(), "type": self.pbRef1XOffsetTypeSel.currentText(),
                            "val": self.pbRef1XOffsetValEdit.text(), "unit": self.pbRef1XOffsetUnitSel.currentText()}
                    refy = {"dir": self.pbRef1YOffsetDirSel.currentText(), "type": self.pbRef1YOffsetTypeSel.currentText(),
                            "val": self.pbRef1YOffsetValEdit.text(), "unit": self.pbRef1YOffsetUnitSel.currentText()}
                    self.newUserInfo.add_ref(self.pbRef1NameEdit.text(), refx, refy)
                    refx = {"dir": self.pbRef2XOffsetDirSel.currentText(), "type": self.pbRef2XOffsetTypeSel.currentText(),
                            "val": self.pbRef2XOffsetValEdit.text(), "unit": self.pbRef2XOffsetUnitSel.currentText()}
                    refy = {"dir": self.pbRef2YOffsetDirSel.currentText(), "type": self.pbRef2YOffsetTypeSel.currentText(),
                            "val": self.pbRef2YOffsetValEdit.text(), "unit": self.pbRef2YOffsetUnitSel.currentText()}
                    self.newUserInfo.add_ref(self.pbRef2NameEdit.text(), refx, refy)
                elif self.pbNRefSel.currentText == '3':
                    refx = {"dir": self.pbRef1XOffsetDirSel.currentText(), "type": self.pbRef1XOffsetTypeSel.currentText(),
                            "val": self.pbRef1XOffsetValEdit.text(), "unit": self.pbRef1XOffsetUnitSel.currentText()}
                    refy = {"dir": self.pbRef1YOffsetDirSel.currentText(), "type": self.pbRef1YOffsetTypeSel.currentText(),
                            "val": self.pbRef1YOffsetValEdit.text(), "unit": self.pbRef1YOffsetUnitSel.currentText()}
                    self.newUserInfo.add_ref(self.pbRef1NameEdit.text(), refx, refy)
                    refx = {"dir": self.pbRef2XOffsetDirSel.currentText(), "type": self.pbRef2XOffsetTypeSel.currentText(),
                            "val": self.pbRef2XOffsetValEdit.text(), "unit": self.pbRef2XOffsetUnitSel.currentText()}
                    refy = {"dir": self.pbRef2YOffsetDirSel.currentText(), "type": self.pbRef2YOffsetTypeSel.currentText(),
                            "val": self.pbRef2YOffsetValEdit.text(), "unit": self.pbRef2YOffsetUnitSel.currentText()}
                    self.newUserInfo.add_ref(self.pbRef2NameEdit.text(), refx, refy)
                    refx = {"dir": self.pbRef3XOffsetDirSel.currentText(), "type": self.pbRef3XOffsetTypeSel.currentText(),
                            "val": self.pbRef3XOffsetValEdit.text(), "unit": self.pbRef3XOffsetUnitSel.currentText()}
                    refy = {"dir": self.pbRef3YOffsetDirSel.currentText(), "type": self.pbRef3YOffsetTypeSel.currentText(),
                            "val": self.pbRef3YOffsetValEdit.text(), "unit": self.pbRef3YOffsetUnitSel.currentText()}
                    self.newUserInfo.add_ref(self.pbRef3NameEdit.text(), refx, refy)
                elif self.pbNRefSel.currentText == '4':
                    refx = {"dir": self.pbRef1XOffsetDirSel.currentText(), "type": self.pbRef1XOffsetTypeSel.currentText(),
                            "val": self.pbRef1XOffsetValEdit.text(), "unit": self.pbRef1XOffsetUnitSel.currentText()}
                    refy = {"dir": self.pbRef1YOffsetDirSel.currentText(), "type": self.pbRef1YOffsetTypeSel.currentText(),
                            "val": self.pbRef1YOffsetValEdit.text(), "unit": self.pbRef1YOffsetUnitSel.currentText()}
                    self.newUserInfo.add_ref(self.pbRef1NameEdit.text(), refx, refy)
                    refx = {"dir": self.pbRef2XOffsetDirSel.currentText(), "type": self.pbRef2XOffsetTypeSel.currentText(),
                            "val": self.pbRef2XOffsetValEdit.text(), "unit": self.pbRef2XOffsetUnitSel.currentText()}
                    refy = {"dir": self.pbRef2YOffsetDirSel.currentText(), "type": self.pbRef2YOffsetTypeSel.currentText(),
                            "val": self.pbRef2YOffsetValEdit.text(), "unit": self.pbRef2YOffsetUnitSel.currentText()}
                    self.newUserInfo.add_ref(self.pbRef2NameEdit.text(), refx, refy)
                    refx = {"dir": self.pbRef3XOffsetDirSel.currentText(), "type": self.pbRef3XOffsetTypeSel.currentText(),
                            "val": self.pbRef3XOffsetValEdit.text(), "unit": self.pbRef3XOffsetUnitSel.currentText()}
                    refy = {"dir": self.pbRef3YOffsetDirSel.currentText(), "type": self.pbRef3YOffsetTypeSel.currentText(),
                            "val": self.pbRef3YOffsetValEdit.text(), "unit": self.pbRef3YOffsetUnitSel.currentText()}
                    self.newUserInfo.add_ref(self.pbRef3NameEdit.text(), refx, refy)
                    refx = {"dir": self.pbRef4XOffsetDirSel.currentText(), "type": self.pbRef4XOffsetTypeSel.currentText(),
                            "val": self.pbRef4XOffsetValEdit.text(), "unit": self.pbRef4XOffsetUnitSel.currentText()}
                    refy = {"dir": self.pbRef4YOffsetDirSel.currentText(), "type": self.pbRef4YOffsetTypeSel.currentText(),
                            "val": self.pbRef4YOffsetValEdit.text(), "unit": self.pbRef4YOffsetUnitSel.currentText()}
                    self.newUserInfo.add_ref(self.pbRef4NameEdit.text(), refx, refy)
                self.dataListModel.appendRow(self.newUserInfo)

        elif self.pbtabs.currentIndex() == 1:
            print("add a new step....")
            new_step = PROCEDURAL_STEP(self.pbActionSel.currentText())
            if self.pbActionSel.currentText() == 'App Page Open':
                new_step.set_app_page(self.pbAppLinkEdit.text(), self.pbPageURLEdit.text())
            elif self.pbActionSel.currentText() == 'Create Data':
                new_step.set_data_name(self.pbDataNameEdit.text())
            elif self.pbActionSel.currentText() == 'Mouse Action':
                new_step.set_mouse_action(self.pbMouseActionSel.currentText(), self.pbMouseActionAmountEdit.text())
            elif self.pbActionSel.currentText() == 'Keyboard Action':
                new_step.set_keyboard_action(self.pbKeyboardActionEdit.text())
            elif self.pbActionSel.currentText() == 'Load Data':
                new_step.set_data_file(self.pbDataFileEdit.text())
            elif self.pbActionSel.currentText() == 'Save Data':
                new_step.set_data_file(self.pbDataFileEdit.text())
            elif self.pbActionSel.currentText() == 'Conditional Step':
                new_step.set_condition_jump(self.pbConditionEdit.text(), self.pbConditionTrueEdit.text(), self.pbConditionFalseEdit.text())
            elif self.pbActionSel.currentText() == 'Jump Step':
                new_step.set_jump(self.pbJumpEdit.text())
            elif self.pbActionSel.currentText() == 'Set Wait':
                new_step.set_wait(self.pbWaittimeEdit.text())
            elif self.pbActionSel.currentText() == 'Run Routine':
                new_step.set_routine(self.pbRoutineEdit.text())
            elif self.pbActionSel.currentText() == 'Run External':
                new_step.set_extern(self.pbExternEdit.text())
            self.stepListModel.appendRow(new_step)

    def ia_save(self):
        print("save a new information....")
        # if this bot already exists, then, this is an update case, else this is a new bot creation case.
        if self.pbtabs.currentIndex() == 0:
            if self.pbInfoSel.currentText() == "Anchor":
                self.newAnchor = ANCHOR(self.pbInfoNameEdit.text())
            elif self.pbInfoSel.currentText() == "Useful Data":
                self.newUserInfo = USER_INFO(self.pbInfoNameEdit.text())
        elif self.pbtabs.currentIndex() == 1:
            print("hohoho")

    def ia_remove(self):
        print("remove a piece of information....")
        # if this bot already exists, then, this is an update case, else this is a new bot creation case.
        if self.pbtabs.currentIndex() == 0:
            if self.pbInfoSel.currentText() == "Anchor":
                self.newAnchor = ANCHOR(self.pbInfoNameEdit.text())
                self.pbRTSel.currentIndex
                self.pbRTSel.addItem('No Ref')
                self.pbRTSel.addItem('By Offset')
                self.pbRTSel.addItem('By Bound Box')

            elif self.pbInfoSel.currentText() == "Useful Data":
                self.newUserInfo = USER_INFO(self.pbInfoNameEdit.text())
        elif self.pbtabs.currentIndex() == 1:
            print("hohoho")

    def show_ref1(self):
        self.pbRef1NameLabel.setVisible(True)
        self.pbRef1NameEdit.setVisible(True)
        self.pbRef1XOffsetDirLabel.setVisible(True)
        self.pbRef1XOffsetDirSel.setVisible(True)
        self.pbRef1XOffsetTypeLabel.setVisible(True)
        self.pbRef1XOffsetTypeSel.setVisible(True)
        self.pbRef1XOffsetValLabel.setVisible(True)
        self.pbRef1XOffsetValEdit.setVisible(True)
        self.pbRef1XOffsetUnitLabel.setVisible(True)
        self.pbRef1XOffsetUnitSel.setVisible(True)
        self.pbRef1YOffsetDirLabel.setVisible(True)
        self.pbRef1YOffsetDirSel.setVisible(True)
        self.pbRef1YOffsetTypeLabel.setVisible(True)
        self.pbRef1YOffsetTypeSel.setVisible(True)
        self.pbRef1YOffsetValLabel.setVisible(True)
        self.pbRef1YOffsetValEdit.setVisible(True)
        self.pbRef1YOffsetUnitLabel.setVisible(True)
        self.pbRef1YOffsetUnitSel.setVisible(True)

    def hide_ref1(self):
        self.pbRef1NameLabel.setVisible(False)
        self.pbRef1NameEdit.setVisible(False)
        self.pbRef1XOffsetDirLabel.setVisible(False)
        self.pbRef1XOffsetDirSel.setVisible(False)
        self.pbRef1XOffsetTypeLabel.setVisible(False)
        self.pbRef1XOffsetTypeSel.setVisible(False)
        self.pbRef1XOffsetValLabel.setVisible(False)
        self.pbRef1XOffsetValEdit.setVisible(False)
        self.pbRef1XOffsetUnitLabel.setVisible(False)
        self.pbRef1XOffsetUnitSel.setVisible(False)
        self.pbRef1YOffsetDirLabel.setVisible(False)
        self.pbRef1YOffsetDirSel.setVisible(False)
        self.pbRef1YOffsetTypeLabel.setVisible(False)
        self.pbRef1YOffsetTypeSel.setVisible(False)
        self.pbRef1YOffsetValLabel.setVisible(False)
        self.pbRef1YOffsetValEdit.setVisible(False)
        self.pbRef1YOffsetUnitLabel.setVisible(False)
        self.pbRef1YOffsetUnitSel.setVisible(False)

    def show_ref2(self):
        self.pbRef2NameLabel.setVisible(True)
        self.pbRef2NameEdit.setVisible(True)
        self.pbRef2XOffsetDirLabel.setVisible(True)
        self.pbRef2XOffsetDirSel.setVisible(True)
        self.pbRef2XOffsetTypeLabel.setVisible(True)
        self.pbRef2XOffsetTypeSel.setVisible(True)
        self.pbRef2XOffsetValLabel.setVisible(True)
        self.pbRef2XOffsetValEdit.setVisible(True)
        self.pbRef2XOffsetUnitLabel.setVisible(True)
        self.pbRef2XOffsetUnitSel.setVisible(True)
        self.pbRef2YOffsetDirLabel.setVisible(True)
        self.pbRef2YOffsetDirSel.setVisible(True)
        self.pbRef2YOffsetTypeLabel.setVisible(True)
        self.pbRef2YOffsetTypeSel.setVisible(True)
        self.pbRef2YOffsetValLabel.setVisible(True)
        self.pbRef2YOffsetValEdit.setVisible(True)
        self.pbRef2YOffsetUnitLabel.setVisible(True)
        self.pbRef2YOffsetUnitSel.setVisible(True)

    def hide_ref2(self):
        self.pbRef2NameLabel.setVisible(False)
        self.pbRef2NameEdit.setVisible(False)
        self.pbRef2XOffsetDirLabel.setVisible(False)
        self.pbRef2XOffsetDirSel.setVisible(False)
        self.pbRef2XOffsetTypeLabel.setVisible(False)
        self.pbRef2XOffsetTypeSel.setVisible(False)
        self.pbRef2XOffsetValLabel.setVisible(False)
        self.pbRef2XOffsetValEdit.setVisible(False)
        self.pbRef2XOffsetUnitLabel.setVisible(False)
        self.pbRef2XOffsetUnitSel.setVisible(False)
        self.pbRef2YOffsetDirLabel.setVisible(False)
        self.pbRef2YOffsetDirSel.setVisible(False)
        self.pbRef2YOffsetTypeLabel.setVisible(False)
        self.pbRef2YOffsetTypeSel.setVisible(False)
        self.pbRef2YOffsetValLabel.setVisible(False)
        self.pbRef2YOffsetValEdit.setVisible(False)
        self.pbRef2YOffsetUnitLabel.setVisible(False)
        self.pbRef2YOffsetUnitSel.setVisible(False)


    def show_ref3(self):
        self.pbRef3NameLabel.setVisible(True)
        self.pbRef3NameEdit.setVisible(True)
        self.pbRef3XOffsetDirLabel.setVisible(True)
        self.pbRef3XOffsetDirSel.setVisible(True)
        self.pbRef3XOffsetTypeLabel.setVisible(True)
        self.pbRef3XOffsetTypeSel.setVisible(True)
        self.pbRef3XOffsetValLabel.setVisible(True)
        self.pbRef3XOffsetValEdit.setVisible(True)
        self.pbRef3XOffsetUnitLabel.setVisible(True)
        self.pbRef3XOffsetUnitSel.setVisible(True)
        self.pbRef3YOffsetDirLabel.setVisible(True)
        self.pbRef3YOffsetDirSel.setVisible(True)
        self.pbRef3YOffsetTypeLabel.setVisible(True)
        self.pbRef3YOffsetTypeSel.setVisible(True)
        self.pbRef3YOffsetValLabel.setVisible(True)
        self.pbRef3YOffsetValEdit.setVisible(True)
        self.pbRef3YOffsetUnitLabel.setVisible(True)
        self.pbRef3YOffsetUnitSel.setVisible(True)

    def hide_ref3(self):
        self.pbRef3NameLabel.setVisible(False)
        self.pbRef3NameEdit.setVisible(False)
        self.pbRef3XOffsetDirLabel.setVisible(False)
        self.pbRef3XOffsetDirSel.setVisible(False)
        self.pbRef3XOffsetTypeLabel.setVisible(False)
        self.pbRef3XOffsetTypeSel.setVisible(False)
        self.pbRef3XOffsetValLabel.setVisible(False)
        self.pbRef3XOffsetValEdit.setVisible(False)
        self.pbRef3XOffsetUnitLabel.setVisible(False)
        self.pbRef3XOffsetUnitSel.setVisible(False)
        self.pbRef3YOffsetDirLabel.setVisible(False)
        self.pbRef3YOffsetDirSel.setVisible(False)
        self.pbRef3YOffsetTypeLabel.setVisible(False)
        self.pbRef3YOffsetTypeSel.setVisible(False)
        self.pbRef3YOffsetValLabel.setVisible(False)
        self.pbRef3YOffsetValEdit.setVisible(False)
        self.pbRef3YOffsetUnitLabel.setVisible(False)
        self.pbRef3YOffsetUnitSel.setVisible(False)


    def show_ref4(self):
        self.pbRef4NameLabel.setVisible(True)
        self.pbRef4NameEdit.setVisible(True)
        self.pbRef4XOffsetDirLabel.setVisible(True)
        self.pbRef4XOffsetDirSel.setVisible(True)
        self.pbRef4XOffsetTypeLabel.setVisible(True)
        self.pbRef4XOffsetTypeSel.setVisible(True)
        self.pbRef4XOffsetValLabel.setVisible(True)
        self.pbRef4XOffsetValEdit.setVisible(True)
        self.pbRef4XOffsetUnitLabel.setVisible(True)
        self.pbRef4XOffsetUnitSel.setVisible(True)
        self.pbRef4YOffsetDirLabel.setVisible(True)
        self.pbRef4YOffsetDirSel.setVisible(True)
        self.pbRef4YOffsetTypeLabel.setVisible(True)
        self.pbRef4YOffsetTypeSel.setVisible(True)
        self.pbRef4YOffsetValLabel.setVisible(True)
        self.pbRef4YOffsetValEdit.setVisible(True)
        self.pbRef4YOffsetUnitLabel.setVisible(True)
        self.pbRef4YOffsetUnitSel.setVisible(True)

    def hide_ref4(self):
        self.pbRef4NameLabel.setVisible(False)
        self.pbRef4NameEdit.setVisible(False)
        self.pbRef4XOffsetDirLabel.setVisible(False)
        self.pbRef4XOffsetDirSel.setVisible(False)
        self.pbRef4XOffsetTypeLabel.setVisible(False)
        self.pbRef4XOffsetTypeSel.setVisible(False)
        self.pbRef4XOffsetValLabel.setVisible(False)
        self.pbRef4XOffsetValEdit.setVisible(False)
        self.pbRef4XOffsetUnitLabel.setVisible(False)
        self.pbRef4XOffsetUnitSel.setVisible(False)
        self.pbRef4YOffsetDirLabel.setVisible(False)
        self.pbRef4YOffsetDirSel.setVisible(False)
        self.pbRef4YOffsetTypeLabel.setVisible(False)
        self.pbRef4YOffsetTypeSel.setVisible(False)
        self.pbRef4YOffsetValLabel.setVisible(False)
        self.pbRef4YOffsetValEdit.setVisible(False)
        self.pbRef4YOffsetUnitLabel.setVisible(False)
        self.pbRef4YOffsetUnitSel.setVisible(False)


    def pbStepPrevNextSel_changed(self):
        if self.pbStepPrevNextSel.currentIndex() == 0:
            self.pbStepPrevNextNameLabel.setText("Previous Step Name:")
        else:
            self.pbStepPrevNextNameLabel.setText("Next Step Name:")


    def pbNRefSel_changed(self):
        if self.pbNRefSel.currentIndex() == 0:
            self.hide_ref1()
            self.hide_ref2()
            self.hide_ref3()
            self.hide_ref4()
        elif self.pbNRefSel.currentIndex() == 1:
            self.show_ref1()
            self.hide_ref2()
            self.hide_ref3()
            self.hide_ref4()
        elif self.pbNRefSel.currentIndex() == 2:
            self.show_ref1()
            self.show_ref2()
            self.hide_ref3()
            self.hide_ref4()
        elif self.pbNRefSel.currentIndex() == 3:
            self.show_ref1()
            self.show_ref2()
            self.show_ref3()
            self.hide_ref4()
        elif self.pbNRefSel.currentIndex() == 4:
            self.show_ref1()
            self.show_ref2()
            self.show_ref3()
            self.show_ref4()


    def IndividualItemChanged(self):
        if self.pbtabs.currentIndex() == 0:
            # user click on Info Tab
            self.IA_Add_button.setText('Add Feature')
            self.IA_Remove_button.setText("Remove Feature")
            self.IA_Save_button.setText("Save Feature")
            self.pbskALWidget.setVisible(True)
            self.pbskDLWidget.setVisible(True)
            self.pbskSLWidget.setVisible(False)

        elif self.pbtabs.currentIndex() == 1:
            # user click on Step Tab
            self.pbskALWidget.setVisible(False)
            self.pbskDLWidget.setVisible(False)
            self.pbskSLWidget.setVisible(True)
            self.IA_Add_button.setText("Add Step")
            self.IA_Remove_button.setText("Remove Step")
            self.IA_Save_button.setText("Save Step")

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
        self.runStopped = False
        runAllSteps(self.currentSkill.get_steps())

    def continue_run(self):
        continueRun(steps, last_step)

    def run_step(self):
        continueRun(steps, last_step)

    def _createAnchorEditAction(self):
        new_action = QtGui.QAction(self)
        new_action.setText("&Edit")
        return new_action

    def _createAnchorCloneAction(self):
        new_action = QtGui.QAction(self)
        new_action.setText("&Clone")
        return new_action

    def _createAnchorDeleteAction(self):
        new_action = QtGui.QAction(self)
        new_action.setText("&Delete")
        return new_action

    def _createUserDataEditAction(self):
        new_action = QtGui.QAction(self)
        new_action.setText("&Edit")
        return new_action

    def _createUserDataCloneAction(self):
        new_action = QtGui.QAction(self)
        new_action.setText("&Clone")
        return new_action

    def _createUserDataDeleteAction(self):
        new_action = QtGui.QAction(self)
        new_action.setText("&Delete")
        return new_action

    def _createStepEditAction(self):
        new_action = QtGui.QAction(self)
        new_action.setText("&Edit")
        return new_action

    def _createStepCloneAction(self):
        new_action = QtGui.QAction(self)
        new_action.setText("&Clone")
        return new_action

    def _createStepDeleteAction(self):
        new_action = QtGui.QAction(self)
        new_action.setText("&Delete")
        return new_action

    def editAnchor(self):
        print("edit anchor")

    def cloneAnchor(self):
        print("clone anchor")

    def deleteAnchor(self):
        # File actions
        msgBox = QtWidgets.QMessageBox()
        msgBox.setText("The anchor will be removed and won't be able recover from it..")
        msgBox.setInformativeText("Are you sure about deleting this anchor?")
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
        msgBox.setText("The step will be removed and won't be able recover from it..")
        msgBox.setInformativeText("Are you sure about deleting this step?")
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
        msgBox.setText("The step will be removed and won't be able recover from it..")
        msgBox.setInformativeText("Are you sure about deleting this step?")
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