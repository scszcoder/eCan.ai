from PySide6.QtCore import (QPointF, QRectF, Qt)
from PySide6.QtGui import (QPainter, QPainterPath, QPen, QPixmap, QPolygonF)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPolygonItem, QGraphicsEllipseItem, QMenu
from gui.diagram.diagram_item_text import DiagramTextItem
from enum import Enum
import math

ITEM_PORT_RADIUS = 3


class EnumPortDir(Enum):
    TOP = 1
    BOTTOM = 2
    RIGHT = 3
    LEFT = 4


class DiagramSubItemPort(QGraphicsEllipseItem):

    def __init__(self, x, y, width, height, direction: EnumPortDir, parent):
        super(DiagramSubItemPort, self).__init__(x, y, width, height, parent)
        self.parent = parent
        self.direction = direction
        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setAcceptHoverEvents(True)

        self.setRect(x, y, width, height)
        self.setStartAngle(0)
        self.setSpanAngle(5760)

        self.setVisible(False)
        self.selected = False

    def paint(self, painter, option, widget=None):
        if self.selected:
            pen = QPen(Qt.blue)
            pen.setWidth(2)
            painter.setPen(pen)
        else:
            pen = QPen(Qt.blue)
            pen.setWidth(1)
            painter.setPen(pen)

        painter.drawEllipse(self.boundingRect())

    def hoverEnterEvent(self, event):
        # 鼠标进入椭圆区域时，设置选中状态为True，触发重绘
        self.selected = True
        self.setCursor(Qt.CrossCursor)
        self.update()

        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        # 鼠标离开椭圆区域时，设置选中状态为False，触发重绘
        self.selected = False
        self.setCursor(Qt.ArrowCursor)
        self.update()

        super().hoverLeaveEvent(event)

    # def mousePressEvent(self, event):
    #     if event.button() == Qt.LeftButton:
    #         pass
    #     return super().mousePressEvent(event)


class DiagramItem(QGraphicsPolygonItem):
    Step, Conditional, StartEnd, Io = range(4)

    def __init__(self, diagramType, contextMenu: QMenu, parent=None):
        super(DiagramItem, self).__init__(parent)

        self.arrows = []

        self.diagramType = diagramType
        self.myContextMenu: QMenu = contextMenu

        self.name = DiagramTextItem(self)
        self.name.setPlainText("hello")
        self.name.setTextInteractionFlags(Qt.TextEditable)
        self.name.setPos(-18, 18)

        self.tag = DiagramTextItem(self)
        self.tag.setPlainText("tag here")
        self.tag.setTextInteractionFlags(Qt.TextEditable)
        self.tag.setPos(-30, -12.5)

        radius = ITEM_PORT_RADIUS
        self.port_bottom = DiagramSubItemPort(0 - radius, 15 - radius, 2 * radius, 2 * radius, EnumPortDir.BOTTOM, self)
        self.port_top = DiagramSubItemPort(0 - radius, -15 - radius, 2 * radius, 2 * radius, EnumPortDir.TOP, self)
        self.port_right = DiagramSubItemPort(50 - radius, 0 - radius, 2 * radius, 2 * radius, EnumPortDir.RIGHT, self)
        self.port_left = DiagramSubItemPort(-50 - radius, 0 - radius, 2 * radius, 2 * radius, EnumPortDir.LEFT, self)

        self.prot_items = [self.port_top, self.port_bottom, self.port_right, self.port_left]

        if self.diagramType == self.StartEnd:
            rect = QRectF(-50, -15, 100, 30)
            radius = 7.5
            path = QPainterPath()
            path.addRoundedRect(rect, radius, radius)
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
        self.setAcceptHoverEvents(True)

    def removeArrow(self, arrow):
        self.arrows = [obj for obj in self.arrows if obj != arrow]

    # def removeArrows(self):
    #     for arrow in self.arrows[:]:
    #         arrow.startItem().removeArrow(arrow)
    #         arrow.endItem().removeArrow(arrow)
    #         self.scene().removeItem(arrow)

    def remove_arrows_items(self):
        for arrow in self.arrows[:]:
            arrow.delete_target_item(self)

    def addArrow(self, new_arrow):
        for arrow in self.arrows[:]:
            if arrow == new_arrow:
                return

        self.arrows.append(new_arrow)

    def redraw_arrows_path(self, event):
        for arrow in self.arrows[:]:
            arrow.redraw_path(self, event)

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

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        # if event.buttons() == Qt.LeftButton:
        #     # offset = event.pos() - event.lastPos()
        #     # print(f"diagram item {self}; mouse event {event}")
        #     # self.redraw_arrows_path(event)
        #     pass

    def itemChange(self, change, value):
        print(f"change:{change};value:{value}")
        # if change == QGraphicsItem.ItemPositionChange:
        #     for arrow in self.arrows:
        #         arrow.updatePosition()

        return value

    def set_ports_visible(self, visible):
        self.port_top.setVisible(visible)
        self.port_bottom.setVisible(visible)
        self.port_right.setVisible(visible)
        self.port_left.setVisible(visible)

    # def calculate_distance(self, p1, p2):
    #     distance = math.sqrt((p2.x() - p1.x()) ** 2 + (p2.y() - p1.y()) ** 2)
    #     return int(distance)

    def closest_sub_item_port(self, point: QPointF) -> DiagramSubItemPort:
        for item in self.prot_items:
            # print((point - item.sceneBoundingRect().center()) .manhattanLength())
            if (point - item.sceneBoundingRect().center()).manhattanLength() <= ITEM_PORT_RADIUS*2:
                return item

        return None

    def closest_edge(self, point: QPointF) -> DiagramSubItemPort:
        distance_top = abs(point.y() - self.sceneBoundingRect().top())
        distance_bottom = abs(point.y() - self.sceneBoundingRect().bottom())
        distance_left = abs(point.x() - self.sceneBoundingRect().left())
        distance_right = abs(point.x() - self.sceneBoundingRect().right())

        min_distance = min(distance_top, distance_bottom, distance_left, distance_right)

        if min_distance == distance_top:
            return self.port_top
        elif min_distance == distance_bottom:
            return self.port_bottom
        elif min_distance == distance_left:
            return self.port_left
        else:
            return self.port_right

    def hoverEnterEvent(self, event):
        self.set_ports_visible(True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.set_ports_visible(False)
        super().hoverLeaveEvent(event)


class DiagramItemGroup:
    def __init__(self, target_item: DiagramItem = None, target_sub_item_port: DiagramSubItemPort = None):
        self.diagram_item = target_item
        self.diagram_sub_item_port = target_sub_item_port
