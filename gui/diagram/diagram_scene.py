from PySide6.QtCore import (Signal, QPointF, QRectF, Qt)
from PySide6.QtGui import (QFont, QPainter, QPen, QColor, QPalette)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsTextItem, QMenu
from gui.diagram.diagram_item import DiagramItem, DiagramSubItemPort, DiagramItemGroup
from gui.diagram.diagram_item_text import DiagramTextItem
from gui.diagram.diagram_item_arrow import DiagramArrowItem
from gui.diagram.diagram_base import EnumItemType
import json


class DiagramScene(QGraphicsScene):
    InsertItem, InsertLine, InsertText, MoveItem, SetTxtBold, SetTxtItalic, SetTxtUnderline = range(7)

    itemInserted = Signal(DiagramItem)

    textInserted = Signal(DiagramTextItem)

    arrowInserted = Signal(DiagramArrowItem)

    itemSelected = Signal(QGraphicsItem)

    def __init__(self, item_menu, parent=None):
        super(DiagramScene, self).__init__(parent)

        self.myItemMenu = item_menu
        self.myMode = self.MoveItem
        self.myItemType = DiagramItem.Step
        self.line = None
        self.textItem = None
        self.myItemColor = QColor(Qt.white)
        self.myTextColor = QColor(Qt.black)
        self.myLineColor = QColor(Qt.black)
        self.myFont: QFont = QFont()
        self.gridSize = 5

    def setLineColor(self, color):
        self.myLineColor = color
        if self.isItemChange(DiagramArrowItem):
            item: DiagramArrowItem = self.selectedItems()[0]
            item.set_color(self.myLineColor)
            self.update()

    def setTextColor(self, color):
        self.myTextColor = color
        if self.isItemChange(DiagramTextItem):
            item = self.selectedItems()[0]
            item.setDefaultTextColor(self.myTextColor)

    def setItemColor(self, color):
        self.myItemColor = color
        if self.isItemChange(DiagramItem):
            item: DiagramItem = self.selectedItems()[0]
            item.setBrush(self.myItemColor)

    def setFont(self, font):
        self.myFont = font
        if self.isItemChange(DiagramTextItem):
            item: DiagramTextItem = self.selectedItems()[0]
            item.set_font(self.myFont)

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
        super(DiagramScene, self).mousePressEvent(mouseEvent)
        if mouseEvent.button() != Qt.LeftButton:
            return

        if self.myMode == self.InsertItem:
            print("inserting a normal item...")
            item = DiagramItem(diagram_type=self.myItemType, context_menu=self.myItemMenu, text_color=self.myTextColor,
                               item_color=self.myItemColor, font=self.myFont, position=mouseEvent.scenePos())
            # item.setBrush(self.myItemColor)
            self.add_diagram_item(item)
            # item.setPos(mouseEvent.scenePos())
            self.itemInserted.emit(item)
        elif self.myMode == self.InsertLine:
            print("inserting a line...")
            if self.isItemChange(DiagramArrowItem):
                self.line = self.selectedItems()[0]

            if self.line is None:
                # 当点击对应的item时候，需要要有选择到 port才能开始画线
                target_item_group = self.query_target_event_items(mouseEvent.scenePos())
                if target_item_group is None or target_item_group.diagram_sub_item_port is not None:
                    self.line = DiagramArrowItem(start_point=mouseEvent.scenePos(),
                                                 line_color=self.myLineColor,
                                                 context_menu=self.myItemMenu,
                                                 target_item_group=target_item_group)

                    self.add_diagram_item(self.line)
            else:
                print("selected existed line")
                if self.line.reselected_start_or_end_point(mouseEvent) is False:
                    print("selected existed line can not be drag")
                    self.line = None

        elif self.myMode == self.InsertText:
            print("inserting a text...")
            item = DiagramTextItem("hello", self.myFont, self.myTextColor, mouseEvent.scenePos(),
                                   False, self.myItemMenu)
            self.add_diagram_item(item)
            self.textInserted.emit(item)

        # super(DiagramScene, self).mousePressEvent(mouseEvent)

    def mouseMoveEvent(self, mouseEvent):
        super().mouseMoveEvent(mouseEvent)
        if self.myMode == self.InsertLine and self.line:
            self.line.update_arrow_path(mouseEvent.scenePos(), self.query_target_event_items(mouseEvent.scenePos()))
        elif self.myMode == self.MoveItem:
            if self.isItemChange(DiagramItem):
                diagram_item: DiagramItem = self.selectedItems()[0]
                diagram_item.redraw_arrows_path(mouseEvent)

        # super().mouseMoveEvent(mouseEvent)

    def mouseReleaseEvent(self, mouseEvent):
        super(DiagramScene, self).mouseReleaseEvent(mouseEvent)
        if self.line and self.myMode == self.InsertLine:
            target_item_group = self.query_target_event_items(mouseEvent.scenePos())
            self.line.end_arrow_path(mouseEvent.scenePos(), target_item_group)
            self.line.setSelected(False)
            if self.line.distance_too_short():
                self.removeItem(self.line)
                print("line is too short removed from scene")
            else:
                self.arrowInserted.emit(self.line)

        self.line = None
        # super(DiagramScene, self).mouseReleaseEvent(mouseEvent)

    def query_target_event_items(self, point: QPointF):
        target_item_group: DiagramItemGroup = None

        items = self.items(point)
        for item in items:
            if isinstance(item, DiagramItem):
                target_item_group = DiagramItemGroup(item, item.closest_sub_item_port(point))
            elif isinstance(item, DiagramSubItemPort):
                target_item_group = DiagramItemGroup(item.parent, item)

        return target_item_group

    def isItemChange(self, type):
        for item in self.selectedItems():
            if isinstance(item, type):
                return True
        return False

    def add_diagram_item(self, item):
        self.addItem(item)

    def remove_diagram_item(self, item):
        print(f"remove item {item} form scene")
        self.removeItem(item)

    # def mydrawBackground(self):
    #     pen =QPen()
    #     rect = QRectF
    #     painter = QPainter
    #     painter.setPen(pen)
    #
    #     left = int(rect.left()) - (int(rect.left()) % self.gridSize)
    #     top = int(rect.top()) - (int(rect.top()) % self.gridSize)
    #     point = QPointF()
    #     points = QtGui.QVector2D(point)
    #     x = left
    #     while x < rect.right():
    #         y = top
    #         while y < rect.bottom():
    #             points.append(QPointF(x,y))
    #             y = y + self.gridSize
    #         x = x + self.gridSize
    #     painter.drawPoints(points.data(), points.size())

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

    def to_json(self):
        items = []

        for item in self.items():
            if isinstance(item, DiagramItem):
                items.append(item.to_dict())
            elif isinstance(item, DiagramTextItem):
                if item.sub_item is False:
                    items.append(item.to_dict())
            elif isinstance(item, DiagramArrowItem):
                items.append(item.to_dict())
            else:
                print(f"filter diagram item to dict error type {item}")

        obj_dict = {
            "items": items
        }

        return json.dumps(obj_dict)

    @classmethod
    def from_json(cls, json_str, context_menu: QMenu):
        items_dict = json.loads(json_str)

        items = []
        for item in items_dict["items"]:
            str_item_type = item["item_type"]
            enum_item_type = EnumItemType[str_item_type]

            if enum_item_type == EnumItemType.Text:
                items.append(DiagramTextItem.from_dict(item, context_menu))
            elif enum_item_type == EnumItemType.Normal:
                items.append(DiagramItem.from_dict(item, context_menu))
            elif enum_item_type == EnumItemType.Arrow:
                items.append(DiagramArrowItem.from_dict(item, context_menu))
            else:
                print(f"diagram scene from json error item type {enum_item_type}")

        return items

