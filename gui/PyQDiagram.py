#############################################################################
##
## Copyright (C) 2013 Riverbank Computing Limited.
## Copyright (C) 2010 Nokia Corporation and/or its subsidiary(-ies).
## All rights reserved.
##
## This file is part of the examples of PyQt.
##
## $QT_BEGIN_LICENSE:BSD$
## You may use this file under the terms of the BSD license as follows:
##
## "Redistribution and use in source and binary forms, with or without
## modification, are permitted provided that the following conditions are
## met:
##   * Redistributions of source code must retain the above copyright
##     notice, this list of conditions and the following disclaimer.
##   * Redistributions in binary form must reproduce the above copyright
##     notice, this list of conditions and the following disclaimer in
##     the documentation and/or other materials provided with the
##     distribution.
##   * Neither the name of Nokia Corporation and its Subsidiary(-ies) nor
##     the names of its contributors may be used to endorse or promote
##     products derived from this software without specific prior written
##     permission.
##
## THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
## "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
## LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
## A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
## OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
## SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
## LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
## DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
## THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
## (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
## OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE."
## $QT_END_LICENSE$
##
#############################################################################

import os
import math

from PySide6.QtCore import (Signal, QLineF, QPointF, QRect, QRectF, QSize,
        QSizeF, Qt)
from PySide6.QtGui import (QAction, QBrush, QColor, QFont, QIcon, QIntValidator, QPainter,
        QPainterPath, QPen, QPixmap, QPolygonF)
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QButtonGroup, QComboBox, \
                    QFontComboBox, QGraphicsItem, QGraphicsLineItem, QGraphicsPolygonItem, \
                            QGraphicsScene, QGraphicsEllipseItem, QGraphicsTextItem, QGraphicsView, QGridLayout, \
                            QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox, QSizePolicy, \
                            QVBoxLayout, QToolBox, QToolButton, QWidget


class Arrow(QGraphicsLineItem):
    def __init__(self, startItem, endItem, parent=None, scene=None):
        super(Arrow, self).__init__(parent, scene)

        self.arrowHead = QPolygonF()

        self.myStartItem = startItem
        self.myEndItem = endItem
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.myColor = Qt.black
        self.setPen(QPen(self.myColor, 2, Qt.SolidLine, Qt.RoundCap,
                Qt.RoundJoin))

    def setColor(self, color):
        self.myColor = color

    def startItem(self):
        return self.myStartItem

    def endItem(self):
        return self.myEndItem

    def boundingRect(self):
        extra = (self.pen().width() + 20) / 2.0
        p1 = self.line().p1()
        p2 = self.line().p2()
        return QRectF(p1, QSizeF(p2.x() - p1.x(), p2.y() - p1.y())).normalized().adjusted(-extra, -extra, extra, extra)

    def shape(self):
        path = super(Arrow, self).shape()
        path.addPolygon(self.arrowHead)
        return path

    def updatePosition(self):
        line = QLineF(self.mapFromItem(self.myStartItem, 0, 0), self.mapFromItem(self.myEndItem, 0, 0))
        self.setLine(line)

    def paint(self, painter, option, widget=None):
        if (self.myStartItem.collidesWithItem(self.myEndItem)):
            return

        myStartItem = self.myStartItem
        myEndItem = self.myEndItem
        myColor = self.myColor
        myPen = self.pen()
        myPen.setColor(self.myColor)
        arrowSize = 20.0
        painter.setPen(myPen)
        painter.setBrush(self.myColor)

        centerLine = QLineF(myStartItem.pos(), myEndItem.pos())
        endPolygon = myEndItem.polygon()
        p1 = endPolygon.first() + myEndItem.pos()

        intersectPoint = QPointF()
        for i in endPolygon:
            p2 = i + myEndItem.pos()
            polyLine = QLineF(p1, p2)
            # intersectType = polyLine.intersect(centerLine, intersectPoint)
            intersectType, intersectPoint = polyLine.intersects(centerLine)
            if intersectType == QLineF.BoundedIntersection:
                break
            p1 = p2

        self.setLine(QLineF(intersectPoint, myStartItem.pos()))
        line = self.line()

        angle = math.acos(line.dx() / line.length())
        if line.dy() >= 0:
            angle = (math.pi * 2.0) - angle

        arrowP1 = line.p1() + QPointF(math.sin(angle + math.pi / 3.0) * arrowSize,
                                        math.cos(angle + math.pi / 3) * arrowSize)
        arrowP2 = line.p1() + QPointF(math.sin(angle + math.pi - math.pi / 3.0) * arrowSize,
                                        math.cos(angle + math.pi - math.pi / 3.0) * arrowSize)

        self.arrowHead.clear()
        for point in [line.p1(), arrowP1, arrowP2]:
            self.arrowHead.append(point)

        painter.drawLine(line)
        painter.drawPolygon(self.arrowHead)
        if self.isSelected():
            painter.setPen(QPen(myColor, 1, Qt.DashLine))
            myLine = QLineF(line)
            myLine.translate(0, 4.0)
            painter.drawLine(myLine)
            myLine.translate(0,-8.0)
            painter.drawLine(myLine)


class DiagramTextItem(QGraphicsTextItem):
    lostFocus = Signal(QGraphicsTextItem)

    selectedChange = Signal(QGraphicsItem)

    def __init__(self, parent=None, scene=None):
        super(DiagramTextItem, self).__init__(parent, scene)

        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemSelectedChange:
            self.selectedChange.emit(self)
        return value

    def focusOutEvent(self, event):
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        self.lostFocus.emit(self)
        super(DiagramTextItem, self).focusOutEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.textInteractionFlags() == Qt.NoTextInteraction:
            self.setTextInteractionFlags(Qt.TextEditorInteraction)
        super(DiagramTextItem, self).mouseDoubleClickEvent(event)


class DiagramItem(QGraphicsPolygonItem):
    Step, Conditional, StartEnd, Io = range(4)

    def __init__(self, diagramType, contextMenu, parent=None):
        super(DiagramItem, self).__init__(parent)

        self.arrows = []

        self.diagramType = diagramType
        self.myContextMenu = contextMenu

        self.name = DiagramTextItem(self)
        self.name.setPlainText("hello")
        self.name.setTextInteractionFlags(Qt.TextEditable)
        self.name.setPos(-10, 15)

        self.tag = DiagramTextItem(self)
        self.tag.setPlainText("tag here")
        self.tag.setTextInteractionFlags(Qt.TextEditable)
        self.tag.setPos(-30, -12.5)


        self.port_south = QGraphicsEllipseItem(self)
        self.port_south.setRect(0, 12, 6, 6)
        self.port_south.setStartAngle(0)
        self.port_south.setSpanAngle(5760)

        self.port_north = QGraphicsEllipseItem(self)
        self.port_north.setRect(0, -18, 6, 6)
        self.port_north.setStartAngle(0)
        self.port_north.setSpanAngle(5760)

        self.port_east = QGraphicsEllipseItem(self)
        self.port_east.setRect(47, 0, 6, 6)
        self.port_east.setStartAngle(0)
        self.port_east.setSpanAngle(5760)

        self.port_west = QGraphicsEllipseItem(self)
        self.port_west.setRect(-53, 0, 6, 6)
        self.port_west.setStartAngle(0)
        self.port_west.setSpanAngle(5760)


        #self.note = DiagramTextItem()


        path = QPainterPath()
        if self.diagramType == self.StartEnd:
            # path.moveTo(200, 50)
            # path.arcTo(150, 0, 50, 50, 0, 90)
            # path.arcTo(50, 0, 50, 50, 90, 90)
            # path.arcTo(50, 50, 50, 50, 180, 90)
            # path.arcTo(150, 50, 50, 50, 270, 90)
            # path.lineTo(200, 25)
            path.moveTo(57.5, 7.5)
            path.arcTo(42.5, -7.5, 15, 15, 0, 90)
            path.arcTo(-27.5, -7.5, 15, 15, 90, 90)
            path.arcTo(-27.5, 7.5, 15, 15, 180, 90)
            path.arcTo(42.5, 7.5, 15, 15, 270, 90)
            path.lineTo(57.5, 7.5)
            self.myPolygon = path.toFillPolygon()
        elif self.diagramType == self.Conditional:
            self.myPolygon = QPolygonF([
                    QPointF(-50, 0), QPointF(0, 15),
                    QPointF(50, 0), QPointF(0, -15),
                    QPointF(-50, 0)])
        elif self.diagramType == self.Step:
            self.myPolygon = QPolygonF([
                    QPointF(-50, -15), QPointF(50, -15),
                    QPointF(50, 15), QPointF(-50, 15),
                    QPointF(-50, -15)])
        else:
            self.myPolygon = QPolygonF([
                    QPointF(-50, -15), QPointF(-35, 15),
                    QPointF(50, 15), QPointF(35, -15),
                    QPointF(-50, -15)])

        self.setPolygon(self.myPolygon)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)

    def removeArrow(self, arrow):
        try:
            self.arrows.remove(arrow)
        except ValueError:
            pass

    def removeArrows(self):
        for arrow in self.arrows[:]:
            arrow.startItem().removeArrow(arrow)
            arrow.endItem().removeArrow(arrow)
            self.scene().removeItem(arrow)

    def addArrow(self, arrow):
        self.arrows.append(arrow)

    def image(self):
        pixmap = QPixmap(250, 250)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setPen(QPen(Qt.black, 8))
        painter.translate(125, 125)
        painter.drawPolyline(self.myPolygon)
        return pixmap

    def contextMenuEvent(self, event):
        self.scene().clearSelection()
        self.setSelected(True)
        self.myContextMenu.exec_(event.screenPos())

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            for arrow in self.arrows:
                arrow.updatePosition()

        return value


class DiagramScene(QGraphicsScene):
    InsertItem, InsertLine, InsertText, MoveItem, SetTxtBold, SetTxtItalic, SetTxtUnderline = range(7)

    itemInserted = Signal(DiagramItem)

    textInserted = Signal(QGraphicsTextItem)

    itemSelected = Signal(QGraphicsItem)

    def __init__(self, itemMenu, parent=None):
        super(DiagramScene, self).__init__(parent)

        self.myItemMenu = itemMenu
        self.myMode = self.MoveItem
        self.myItemType = DiagramItem.Step
        self.line = None
        self.textItem = None
        self.myItemColor = Qt.white
        self.myTextColor = Qt.black
        self.myLineColor = Qt.black
        self.myFont = QFont()
        self.gridSize = 5

    def setLineColor(self, color):
        self.myLineColor = color
        if self.isItemChange(Arrow):
            item = self.selectedItems()[0]
            item.setColor(self.myLineColor)
            self.update()

    def setTextColor(self, color):
        self.myTextColor = color
        if self.isItemChange(DiagramTextItem):
            item = self.selectedItems()[0]
            item.setDefaultTextColor(self.myTextColor)

    def setItemColor(self, color):
        self.myItemColor = color
        if self.isItemChange(DiagramItem):
            item = self.selectedItems()[0]
            item.setBrush(self.myItemColor)

    def setFont(self, font):
        self.myFont = font
        if self.isItemChange(DiagramTextItem):
            item = self.selectedItems()[0]
            item.setFont(self.myFont)

    def setMode(self, mode):
        self.myMode = mode

    def setItemType(self, type):
        self.myItemType = type

    def editorLostFocus(self, item):
        cursor = item.textCursor()
        cursor.clearSelection()
        item.setTextCursor(cursor)

        if item.toPlainText():
            self.removeItem(item)
            item.deleteLater()

    def mousePressEvent(self, mouseEvent):
        if (mouseEvent.button() != Qt.LeftButton):
            return

        if self.myMode == self.InsertItem:
            item = DiagramItem(self.myItemType, self.myItemMenu)
            print("creating item type:", self.myItemType)
            item.setBrush(self.myItemColor)
            self.addItem(item)
            item.setPos(mouseEvent.scenePos())
            self.itemInserted.emit(item)
        elif self.myMode == self.InsertLine:
            print("inserting a line...")
            self.line = QGraphicsLineItem(QLineF(mouseEvent.scenePos(),
                    mouseEvent.scenePos()))
            self.line.setPen(QPen(self.myLineColor, 2))
            #self.addItem(self.line)
            self.addLine(self.line.line())
        elif self.myMode == self.InsertText:
            print("inserting a text...")
            textItem = DiagramTextItem()
            textItem.setFont(self.myFont)
            #textItem.setTextInteractionFlags(Qt.TextEditorInteraction)
            textItem.setTextInteractionFlags(Qt.TextEditable)
            textItem.setZValue(1000.0)
            textItem.lostFocus.connect(self.editorLostFocus)
            textItem.selectedChange.connect(self.itemSelected)
            #self.addItem(textItem)
            #self.addText(textItem.toPlainText(), self.myFont)
            txtItem=self.addText("hello", self.myFont)
            #textItem.setDefaultTextColor(self.myTextColor)
            #textItem.setPos(mouseEvent.scenePos())
            #self.textInserted.emit(textItem)
            txtItem.setTextInteractionFlags(Qt.TextEditable)
            txtItem.setZValue(1000.0)
            #txtItem.lostFocus.connect(self.editorLostFocus)
            #txtItem.selectedChange.connect(self.itemSelected)
            txtItem.setDefaultTextColor(self.myTextColor)
            txtItem.setFont(self.myFont)
            txtItem.setPos(mouseEvent.scenePos())
            self.textInserted.emit(txtItem)

        super(DiagramScene, self).mousePressEvent(mouseEvent)

    def mouseMoveEvent(self, mouseEvent):
        if self.myMode == self.InsertLine and self.line:
            newLine = QLineF(self.line.line().p1(), mouseEvent.scenePos())
            self.line.setLine(newLine)
        elif self.myMode == self.MoveItem:
            super(DiagramScene, self).mouseMoveEvent(mouseEvent)

    def mouseReleaseEvent(self, mouseEvent):
        if self.line and self.myMode == self.InsertLine:
            startItems = self.items(self.line.line().p1())
            if len(startItems) and startItems[0] == self.line:
                startItems.pop(0)
            endItems = self.items(self.line.line().p2())
            if len(endItems) and endItems[0] == self.line:
                endItems.pop(0)

            self.removeItem(self.line)
            self.line = None

            if len(startItems) and len(endItems) and \
                    isinstance(startItems[0], DiagramItem) and \
                    isinstance(endItems[0], DiagramItem) and \
                    startItems[0] != endItems[0]:
                startItem = startItems[0]
                endItem = endItems[0]
                arrow = Arrow(startItem, endItem)
                arrow.setColor(self.myLineColor)
                startItem.addArrow(arrow)
                endItem.addArrow(arrow)
                arrow.setZValue(-1000.0)
                self.addItem(arrow)
                arrow.updatePosition()

        self.line = None
        super(DiagramScene, self).mouseReleaseEvent(mouseEvent)

    def isItemChange(self, type):
        for item in self.selectedItems():
            if isinstance(item, type):
                return True
        return False


    def mydrawBackground(self):
        pen =QPen()
        rect = QRectF
        painter = QPainter
        painter.setPen(pen)

        left = int(rect.left()) - (int(rect.left()) % self.gridSize)
        top = int(rect.top()) - (int(rect.top()) % self.gridSize)
        point = QPointF()
        points = QtGui.QVector2D(point)
        x = left
        while x < rect.right():
            y = top
            while y < rect.bottom():
                points.append(QPointF(x,y));
                y = y + self.gridSize
            x = x + self.gridSize
        painter.drawPoints(points.data(), points.size());

    # CustomRectItem
    # change: GraphicsItemChange
    # value: QVariant
    # ref: https://www.walletfox.com/course/qgraphicsitemsnaptogrid.php
    def itemChange(self, mouseEvent, change, value, ItemPositionChange):
        if change == ItemPositionChange: #and scene():
            newPos = QPointF()
            newPos = value.toPointF()
            if mouseEvent.button() != Qt.LeftButton: # and scene():

                #customScene = scene()
                xV = round(newPos.x() / self.gridSize) * self.gridSize
                yV = round(newPos.y() / self.gridSize) * self.gridSize
                return QPointF(xV, yV)
            else:
                return newPos
        else:
            return QGraphicsItem.itemChange(change, value)


class PyQDiagram(QWidget):
    InsertTextButton = 10

    def __init__(self):
        super(PyQDiagram, self).__init__()
        self.homepath = os.environ.get("ECBOT_HOME")
        if self.homepath[len(self.homepath)-1] == "/":
            self.homepath = self.homepath[:len(self.homepath)-1]

        self.createActions()
        self.createMenus()
        # self.createMenuBars()
        self.createToolBox()

        self.scene = DiagramScene(self.itemMenu)
        #self.scene.setSceneRect(QRectF(0, 0, 5000, 5000))
        self.scene.setSceneRect(QRectF(0, 0, 500, 500))
        self.scene.itemInserted.connect(self.itemInserted)
        self.scene.textInserted.connect(self.textInserted)
        self.scene.itemSelected.connect(self.itemSelected)

        #self.createToolbars()
        self.createPseudoToolbars()
        self.test_label = QtWidgets.QLabel("Houston Houston", alignment=QtCore.Qt.AlignLeft)
        layout = QHBoxLayout()
        mainLayout = QVBoxLayout()
        #layout.addWidget(self.test_label)
        layout.addWidget(self.toolBox)
        self.view = QGraphicsView(self.scene)
        self.view.setRubberBandSelectionMode(Qt.IntersectsItemBoundingRect)
        self.view.setDragMode(QGraphicsView.RubberBandDrag)
        layout.addWidget(self.view)
        mainLayout.addLayout(self.ToolBarLayout)
        mainLayout.addLayout(layout)

        self.widget = QWidget()
        self.widget.setLayout(mainLayout)
        print("what????")

        #self.setCentralWidget(self.widget)
        # self.setWindowTitle("Diagramscene")

    def backgroundButtonGroupClicked(self, button):
        buttons = self.backgroundButtonGroup.buttons()
        for myButton in buttons:
            if myButton != button:
                button.setChecked(False)

        text = button.text()
        if text == "Blue Grid":
            self.scene.setBackgroundBrush(QBrush(QPixmap(self.homepath + 'resource/images/background1.png')))
        elif text == "White Grid":
            self.scene.setBackgroundBrush(QBrush(QPixmap(self.homepath + 'resource/images/background2.png')))
        elif text == "Gray Grid":
            self.scene.setBackgroundBrush(QBrush(QPixmap(self.homepath + 'resource/images/background3.png')))
        else:
            self.scene.setBackgroundBrush(QBrush(QPixmap(self.homepath + 'resource/images/background4.png')))

        #self.scene.update()
        #self.view.update()

    #def buttonGroupClicked(self, id):
    def buttonGroupClicked(self, button):
        print("clicked:", button)
        buttons = self.buttonGroup.buttons()
        for mbutton in buttons:
            #if self.buttonGroup.button(id) != mbutton:
            if button != mbutton:
                button.setChecked(False)

        #if id == self.InsertTextButton:
        if self.buttonGroup.id(button) == self.InsertTextButton:
            self.scene.setMode(DiagramScene.InsertText)
        else:
            #self.scene.setItemType(id)
            self.scene.setItemType(self.buttonGroup.id(button))
            self.scene.setMode(DiagramScene.InsertItem)

    def deleteItem(self):
        for item in self.scene.selectedItems():
            if isinstance(item, DiagramItem):
                item.removeArrows()
            self.scene.removeItem(item)

    def pointerGroupClicked(self, i):
        self.scene.setMode(self.pointerTypeGroup.checkedId())

    def txtPropertyGroupClicked(self, i):
        self.handleFontChange()

    def bringToFront(self):
        if not self.scene.selectedItems():
            return

        selectedItem = self.scene.selectedItems()[0]
        overlapItems = selectedItem.collidingItems()

        zValue = 0
        for item in overlapItems:
            if (item.zValue() >= zValue and isinstance(item, DiagramItem)):
                zValue = item.zValue() + 0.1
        selectedItem.setZValue(zValue)

    def sendToBack(self):
        if not self.scene.selectedItems():
            return

        selectedItem = self.scene.selectedItems()[0]
        overlapItems = selectedItem.collidingItems()

        zValue = 0
        for item in overlapItems:
            if (item.zValue() <= zValue and isinstance(item, DiagramItem)):
                zValue = item.zValue() - 0.1
        selectedItem.setZValue(zValue)

    def itemInserted(self, item):
        print("inserted item:", item, ">>", item.diagramType)
        self.pointerTypeGroup.button(DiagramScene.MoveItem).setChecked(True)
        self.scene.setMode(self.pointerTypeGroup.checkedId())
        #self.buttonGroup.button(item.diagramType).setChecked(False)
        self.buttonGroup.button(item.diagramType).setChecked(False)

    def textInserted(self, item):
        self.buttonGroup.button(self.InsertTextButton).setChecked(False)
        self.scene.setMode(self.pointerTypeGroup.checkedId())

    def currentFontChanged(self, font):
        self.handleFontChange()

    def fontSizeChanged(self, font):
        self.handleFontChange()

    def sceneScaleChanged(self, scale):
        scaleString = self.sceneScaleCombo.currentText()
        print("scale changed to: ", scaleString)
        newScale = float(scaleString[:scaleString.index("%")]) / 100.0
        print("scale number:" + str(newScale))
        # newScale = scale.left(scale.indexOf("%")).toDouble()[0] / 100.0
        #oldMatrix = self.view.matrix()
        oldMatrix = self.view.transform()
        # self.view.resetMatrix()
        self.view.resetTransform()
        self.view.translate(oldMatrix.dx(), oldMatrix.dy())
        self.view.scale(newScale, newScale)

    def textColorChanged(self):
        self.textAction = self.sender()
        self.fontColorToolButton.setIcon(
                self.createColorToolButtonIcon(self.homepath + 'resource/images/textpointer.png',
                        QColor(self.textAction.data())))
        self.textButtonTriggered()

    def itemColorChanged(self):
        self.fillAction = self.sender()
        self.fillColorToolButton.setIcon(
                self.createColorToolButtonIcon( self.homepath + 'resource/images/floodfill.png',
                        QColor(self.fillAction.data())))
        self.fillButtonTriggered()

    def lineColorChanged(self):
        self.lineAction = self.sender()
        self.lineColorToolButton.setIcon(
                self.createColorToolButtonIcon(self.homepath + 'resource/images/linecolor.png',
                        QColor(self.lineAction.data())))
        self.lineButtonTriggered()

    def textButtonTriggered(self):
        self.scene.setTextColor(QColor(self.textAction.data()))

    def fillButtonTriggered(self):
        self.scene.setItemColor(QColor(self.fillAction.data()))

    def lineButtonTriggered(self):
        self.scene.setLineColor(QColor(self.lineAction.data()))

    def handleFontChange(self):
        font = self.fontCombo.currentFont()
        font.setPointSize(int(self.fontSizeCombo.currentText()))
        #if self.boldAction.isChecked():
        if self.txtBoldButton.isChecked():
            font.setWeight(QFont.Bold)
        else:
            font.setWeight(QFont.Normal)
        #font.setItalic(self.italicAction.isChecked())
        #font.setUnderline(self.underlineAction.isChecked())
        font.setItalic(self.txtItalicButton.isChecked())
        font.setUnderline(self.txtUnderlineButton.isChecked())

        self.scene.setFont(font)

    def itemSelected(self, item):
        font = item.font()
        color = item.defaultTextColor()
        self.fontCombo.setCurrentFont(font)
        self.fontSizeCombo.setEditText(str(font.pointSize()))
        self.boldAction.setChecked(font.weight() == QFont.Bold)
        self.italicAction.setChecked(font.italic())
        self.underlineAction.setChecked(font.underline())

    def about(self):
        QMessageBox.about(self, "About Diagram Scene",
                "The <b>Diagram Scene</b> example shows use of the graphics framework.")

    def createToolBox(self):
        self.buttonGroup = QButtonGroup()
        self.buttonGroup.setExclusive(False)
        #self.buttonGroup.buttonClicked[int].connect(self.buttonGroupClicked)
        self.buttonGroup.buttonClicked.connect(self.buttonGroupClicked)

        layout = QGridLayout()
        layout.addWidget(self.createCellWidget("Conditional", DiagramItem.Conditional),
                0, 0)
        layout.addWidget(self.createCellWidget("Process", DiagramItem.Step), 0,
                1)
        layout.addWidget(self.createCellWidget("Input/Output", DiagramItem.Io),
                1, 0)
        layout.addWidget(self.createCellWidget("Start/End", DiagramItem.StartEnd),
                1, 1)

        textButton = QToolButton()
        textButton.setCheckable(True)
        self.buttonGroup.addButton(textButton, self.InsertTextButton)
        textButton.setIcon(QIcon(QPixmap(self.homepath + 'resource/images/textpointer.png').scaled(30, 30)))
        textButton.setIconSize(QSize(32, 32))

        textLayout = QGridLayout()
        textLayout.addWidget(textButton, 0, 0, Qt.AlignHCenter)
        textLayout.addWidget(QLabel("Text"), 1, 0, Qt.AlignCenter)
        textWidget = QWidget()
        textWidget.setLayout(textLayout)
        layout.addWidget(textWidget, 2, 0)

        layout.setRowStretch(3, 10)
        layout.setColumnStretch(2, 10)

        itemWidget = QWidget()
        itemWidget.setLayout(layout)

        self.backgroundButtonGroup = QButtonGroup()
        self.backgroundButtonGroup.buttonClicked.connect(self.backgroundButtonGroupClicked)

        backgroundLayout = QGridLayout()
        backgroundLayout.addWidget(self.createBackgroundCellWidget("Blue Grid",
                self.homepath + 'resource/images/background1.png'), 0, 0)
        backgroundLayout.addWidget(self.createBackgroundCellWidget("White Grid",
                self.homepath + 'resource/images/background2.png'), 0, 1)
        backgroundLayout.addWidget(self.createBackgroundCellWidget("Gray Grid",
                self.homepath + 'resource/images/background3.png'), 1, 0)
        backgroundLayout.addWidget(self.createBackgroundCellWidget("No Grid",
                self.homepath + 'resource/images/background4.png'), 1, 1)

        backgroundLayout.setRowStretch(2, 10)
        backgroundLayout.setColumnStretch(2, 10)

        backgroundWidget = QWidget()
        backgroundWidget.setLayout(backgroundLayout)

        self.toolBox = QToolBox()
        self.toolBox.setSizePolicy(QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Ignored))
        self.toolBox.setMinimumWidth(itemWidget.sizeHint().width())
        self.toolBox.addItem(itemWidget, "Basic Flowchart Shapes")
        self.toolBox.addItem(backgroundWidget, "Backgrounds")

    def createActions(self):
        self.toFrontAction = QAction(
                QIcon(self.homepath + 'resource/images/bringtofront.png'), "Bring to &Front",
                self, shortcut="Ctrl+F", statusTip="Bring item to front",
                triggered=self.bringToFront)

        self.sendBackAction = QAction(
                QIcon(self.homepath + 'resource/images/sendtoback.png'), "Send to &Back", self,
                shortcut="Ctrl+B", statusTip="Send item to back",
                triggered=self.sendToBack)

        self.deleteAction = QAction(QIcon(self.homepath + 'resource/images/delete.png'),
                "&Delete", self, shortcut="Delete",
                statusTip="Delete item from diagram",
                triggered=self.deleteItem)

        self.exitAction = QAction("E&xit", self, shortcut="Ctrl+X",
                statusTip="Quit Scenediagram example", triggered=self.close)

        self.boldAction = QAction(QIcon(self.homepath + 'resource/images/bold.png'),
                "Bold", self, checkable=True, shortcut="Ctrl+B",
                triggered=self.handleFontChange)

        self.italicAction = QAction(QIcon(self.homepath + 'resource/images/italic.png'),
                "Italic", self, checkable=True, shortcut="Ctrl+I",
                triggered=self.handleFontChange)

        self.underlineAction = QAction(
                QIcon(self.homepath + 'resource/images/underline.png'), "Underline", self,
                checkable=True, shortcut="Ctrl+U",
                triggered=self.handleFontChange)

        self.aboutAction = QAction("A&bout", self, shortcut="Ctrl+B",
                triggered=self.about)

    def createMenus(self):
        self.itemMenu = QMenu("&Item")
        self.itemMenu.addAction(self.deleteAction)
        self.itemMenu.addSeparator()
        self.itemMenu.addAction(self.toFrontAction)
        self.itemMenu.addAction(self.sendBackAction)

    def createMenuBars(self):
        self.fileMenu = self.menuBar().addMenu("&File")
        self.fileMenu.addAction(self.exitAction)

        self.menuBar().addMenu(self.itemMenu)

        self.aboutMenu = self.menuBar().addMenu("&Help")
        self.aboutMenu.addAction(self.aboutAction)

    def createToolbars(self):
        self.editToolBar = self.addToolBar("Edit")
        self.editToolBar.addAction(self.deleteAction)
        self.editToolBar.addAction(self.toFrontAction)
        self.editToolBar.addAction(self.sendBackAction)

        self.fontCombo = QFontComboBox()
        self.fontCombo.currentFontChanged.connect(self.currentFontChanged)

        self.fontSizeCombo = QComboBox()
        self.fontSizeCombo.setEditable(True)
        for i in range(8, 30, 2):
            self.fontSizeCombo.addItem(str(i))
        validator = QIntValidator(2, 64, self)
        self.fontSizeCombo.setValidator(validator)
        self.fontSizeCombo.currentIndexChanged.connect(self.fontSizeChanged)

        self.fontColorToolButton = QToolButton()
        self.fontColorToolButton.setPopupMode(QToolButton.MenuButtonPopup)
        self.fontColorToolButton.setMenu(
                self.createColorMenu(self.textColorChanged, Qt.black))
        self.textAction = self.fontColorToolButton.menu().defaultAction()
        self.fontColorToolButton.setIcon(
                self.createColorToolButtonIcon(self.homepath + 'resource/images/textpointer.png',
                        Qt.black))
        self.fontColorToolButton.setAutoFillBackground(True)
        self.fontColorToolButton.clicked.connect(self.textButtonTriggered)

        self.fillColorToolButton = QToolButton()
        self.fillColorToolButton.setPopupMode(QToolButton.MenuButtonPopup)
        self.fillColorToolButton.setMenu(
                self.createColorMenu(self.itemColorChanged, Qt.white))
        self.fillAction = self.fillColorToolButton.menu().defaultAction()
        self.fillColorToolButton.setIcon(
                self.createColorToolButtonIcon(self.homepath + 'resource/images/floodfill.png',
                        Qt.white))
        self.fillColorToolButton.clicked.connect(self.fillButtonTriggered)

        self.lineColorToolButton = QToolButton()
        self.lineColorToolButton.setPopupMode(QToolButton.MenuButtonPopup)
        self.lineColorToolButton.setMenu(
                self.createColorMenu(self.lineColorChanged, Qt.black))
        self.lineAction = self.lineColorToolButton.menu().defaultAction()
        self.lineColorToolButton.setIcon(
                self.createColorToolButtonIcon(self.homepath + 'resource/images/linecolor.png',
                        Qt.black))
        self.lineColorToolButton.clicked.connect(self.lineButtonTriggered)

        self.textToolBar = self.addToolBar("Font")
        self.textToolBar.addWidget(self.fontCombo)
        self.textToolBar.addWidget(self.fontSizeCombo)
        self.textToolBar.addAction(self.boldAction)
        self.textToolBar.addAction(self.italicAction)
        self.textToolBar.addAction(self.underlineAction)

        self.colorToolBar = self.addToolBar("Color")
        self.colorToolBar.addWidget(self.fontColorToolButton)
        self.colorToolBar.addWidget(self.fillColorToolButton)
        self.colorToolBar.addWidget(self.lineColorToolButton)

        pointerButton = QToolButton()
        pointerButton.setCheckable(True)
        pointerButton.setChecked(True)
        pointerButton.setIcon(QIcon(self.homepath + 'resource/images/pointer.png'))
        linePointerButton = QToolButton()
        linePointerButton.setCheckable(True)
        linePointerButton.setIcon(QIcon(self.homepath + 'resource/images/linepointer.png'))

        self.pointerTypeGroup = QButtonGroup()
        self.pointerTypeGroup.addButton(pointerButton, DiagramScene.MoveItem)
        self.pointerTypeGroup.addButton(linePointerButton, DiagramScene.InsertLine)
        # self.pointerTypeGroup.buttonClicked[int].connect(self.pointerGroupClicked)
        self.pointerTypeGroup.buttonClicked.connect(self.pointerGroupClicked)


        self.sceneScaleCombo = QComboBox()
        self.sceneScaleCombo.addItems(["50%", "75%", "100%", "125%", "150%"])
        self.sceneScaleCombo.setCurrentIndex(2)
        self.sceneScaleCombo.currentIndexChanged[str].connect(self.sceneScaleChanged)

        self.pointerToolbar = self.addToolBar("Pointer type")
        self.pointerToolbar.addWidget(pointerButton)
        self.pointerToolbar.addWidget(linePointerButton)
        self.pointerToolbar.addWidget(self.sceneScaleCombo)

    def createPseudoToolbars(self):
        self.ToolBarLayout = QHBoxLayout()
        self.fontCombo = QFontComboBox()
        self.fontCombo.currentFontChanged.connect(self.currentFontChanged)

        self.fontSizeCombo = QComboBox()
        self.fontSizeCombo.setEditable(True)
        for i in range(8, 30, 2):
            self.fontSizeCombo.addItem(str(i))
        validator = QIntValidator(2, 64, self)
        self.fontSizeCombo.setValidator(validator)
        self.fontSizeCombo.currentIndexChanged.connect(self.fontSizeChanged)

        self.fontColorToolButton = QToolButton()
        self.fontColorToolButton.setPopupMode(QToolButton.MenuButtonPopup)
        self.fontColorToolButton.setMenu(
            self.createColorMenu(self.textColorChanged, Qt.black))
        self.textAction = self.fontColorToolButton.menu().defaultAction()
        self.fontColorToolButton.setIcon(
            self.createColorToolButtonIcon(self.homepath + 'resource/images/textpointer.png',
                                           Qt.black))
        self.fontColorToolButton.setAutoFillBackground(True)
        self.fontColorToolButton.clicked.connect(self.textButtonTriggered)

        self.fillColorToolButton = QToolButton()
        self.fillColorToolButton.setPopupMode(QToolButton.MenuButtonPopup)
        self.fillColorToolButton.setMenu(
            self.createColorMenu(self.itemColorChanged, Qt.white))
        self.fillAction = self.fillColorToolButton.menu().defaultAction()
        self.fillColorToolButton.setIcon(
            self.createColorToolButtonIcon(self.homepath + 'resource/images/floodfill.png',
                                           Qt.white))
        self.fillColorToolButton.clicked.connect(self.fillButtonTriggered)

        self.lineColorToolButton = QToolButton()
        self.lineColorToolButton.setPopupMode(QToolButton.MenuButtonPopup)
        self.lineColorToolButton.setMenu(
            self.createColorMenu(self.lineColorChanged, Qt.black))
        self.lineAction = self.lineColorToolButton.menu().defaultAction()
        self.lineColorToolButton.setIcon(
            self.createColorToolButtonIcon(self.homepath + 'resource/images/linecolor.png',
                                           Qt.black))
        self.lineColorToolButton.clicked.connect(self.lineButtonTriggered)

        self.txtBoldButton = QToolButton()
        self.txtBoldButton.setCheckable(True)
        self.txtBoldButton.setChecked(False)
        self.txtBoldButton.setIcon(QIcon(self.homepath + 'resource/images/bold.png'))
        self.txtItalicButton = QToolButton()
        self.txtItalicButton.setCheckable(True)
        self.txtItalicButton.setChecked(False)
        self.txtItalicButton.setIcon(QIcon(self.homepath + 'resource/images/italic.png'))
        self.txtUnderlineButton = QToolButton()
        self.txtUnderlineButton.setCheckable(True)
        self.txtUnderlineButton.setChecked(False)
        self.txtUnderlineButton.setIcon(QIcon(self.homepath + 'resource/images/underline.png'))

        self.textToolBarLayout = QtWidgets.QHBoxLayout()
        self.textToolBarLayout.addWidget(self.fontCombo)
        self.textToolBarLayout.addWidget(self.fontSizeCombo)
        self.textToolBarLayout.addWidget(self.txtBoldButton)
        self.textToolBarLayout.addWidget(self.txtItalicButton)
        self.textToolBarLayout.addWidget(self.txtUnderlineButton)

        self.colorToolBarLayout = QtWidgets.QHBoxLayout()
        self.colorToolBarLayout.addWidget(self.fontColorToolButton)
        self.colorToolBarLayout.addWidget(self.fillColorToolButton)
        self.colorToolBarLayout.addWidget(self.lineColorToolButton)

        pointerButton = QToolButton()
        pointerButton.setCheckable(True)
        pointerButton.setChecked(True)
        pointerButton.setIcon(QIcon(self.homepath + 'resource/images/pointer.png'))
        linePointerButton = QToolButton()
        linePointerButton.setCheckable(True)
        linePointerButton.setIcon(QIcon(self.homepath + 'resource/images/linepointer.png'))

        self.txtPropertyGroup = QButtonGroup()
        self.txtPropertyGroup.addButton(self.txtBoldButton, DiagramScene.SetTxtBold)
        self.txtPropertyGroup.addButton(self.txtItalicButton, DiagramScene.SetTxtItalic)
        self.txtPropertyGroup.addButton(self.txtUnderlineButton, DiagramScene.SetTxtUnderline)
        self.txtPropertyGroup.buttonClicked.connect(self.txtPropertyGroupClicked)

        self.pointerTypeGroup = QButtonGroup()
        self.pointerTypeGroup.addButton(pointerButton, DiagramScene.MoveItem)
        self.pointerTypeGroup.addButton(linePointerButton, DiagramScene.InsertLine)
        # self.pointerTypeGroup.buttonClicked[int].connect(self.pointerGroupClicked)
        self.pointerTypeGroup.buttonClicked.connect(self.pointerGroupClicked)

        self.sceneScaleCombo = QComboBox()
        self.sceneScaleCombo.addItems(["50%", "75%", "100%", "125%", "150%"])
        self.sceneScaleCombo.setCurrentIndex(2)
        #self.sceneScaleCombo.currentIndexChanged[str].connect(self.sceneScaleChanged)
        self.sceneScaleCombo.currentIndexChanged.connect(self.sceneScaleChanged)

        self.pointerToolbarLayout = QHBoxLayout()
        self.pointerToolbarLayout.addWidget(pointerButton)
        self.pointerToolbarLayout.addWidget(linePointerButton)
        self.pointerToolbarLayout.addWidget(self.sceneScaleCombo)

        self.ToolBarLayout.addLayout(self.textToolBarLayout)
        self.ToolBarLayout.addLayout(self.colorToolBarLayout)
        self.ToolBarLayout.addLayout(self.pointerToolbarLayout)

    def createBackgroundCellWidget(self, text, image):
        button = QToolButton()
        button.setText(text)
        button.setIcon(QIcon(image))
        button.setIconSize(QSize(50, 50))
        button.setCheckable(True)
        self.backgroundButtonGroup.addButton(button)

        layout = QGridLayout()
        layout.addWidget(button, 0, 0, Qt.AlignHCenter)
        layout.addWidget(QLabel(text), 1, 0, Qt.AlignCenter)

        widget = QWidget()
        widget.setLayout(layout)

        return widget

    def createCellWidget(self, text, diagramType):
        item = DiagramItem(diagramType, self.itemMenu)
        print("creating widget type:", diagramType)
        icon = QIcon(item.image())

        button = QToolButton()
        button.setIcon(icon)
        button.setIconSize(QSize(32, 32))
        button.setCheckable(True)
        self.buttonGroup.addButton(button, diagramType)

        layout = QGridLayout()
        layout.addWidget(button, 0, 0, Qt.AlignHCenter)
        layout.addWidget(QLabel(text), 1, 0, Qt.AlignCenter)

        widget = QWidget()
        widget.setLayout(layout)

        return widget

    def createColorMenu(self, slot, defaultColor):
        colors = [Qt.black, Qt.white, Qt.red, Qt.blue, Qt.yellow]
        names = ["black", "white", "red", "blue", "yellow"]

        colorMenu = QMenu(self)
        for color, name in zip(colors, names):
            action = QAction(self.createColorIcon(color), name, self,
                    triggered=slot)
            action.setData(QColor(color))
            colorMenu.addAction(action)
            if color == defaultColor:
                colorMenu.setDefaultAction(action)
        return colorMenu

    def createColorToolButtonIcon(self, imageFile, color):
        pixmap = QPixmap(50, 80)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        image = QPixmap(imageFile)
        target = QRect(0, 0, 50, 60)
        source = QRect(0, 0, 42, 42)
        painter.fillRect(QRect(0, 60, 50, 80), color)
        painter.drawPixmap(target, image, source)
        painter.end()

        return QIcon(pixmap)

    def createColorIcon(self, color):
        pixmap = QPixmap(20, 20)
        painter = QPainter(pixmap)
        painter.setPen(Qt.NoPen)
        painter.fillRect(QRect(0, 0, 20, 20), color)
        painter.end()

        return QIcon(pixmap)
