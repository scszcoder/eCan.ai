from PySide6.QtCore import (QPointF, QRectF, Qt)
from PySide6.QtGui import (QPainterPath, QColor, QFont, QPen, QPolygonF)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPolygonItem, QGraphicsEllipseItem, QMenu

from gui.skfc.diagram_item_text import DiagramTextItem
from gui.skfc.skfc_base import EnumItemType, SkFCBase
from enum import Enum

from skill.steps.step_base import StepBase

ITEM_PORT_RADIUS = 3


class EnumPortDir(Enum):
    TOP = 1
    BOTTOM = 2
    RIGHT = 3
    LEFT = 4

    @staticmethod
    def enum_name(obj):
        if obj is not None:
            if isinstance(obj, EnumPortDir):
                return obj.name
            raise TypeError(f"{obj} is not JSON serializable of EnumPortDir")

        return None

    @staticmethod
    def enum_name_to_item_port(name):
        if name is not None:
            return EnumPortDir[name]

        return None


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


class DiagramNormalItem(QGraphicsPolygonItem):
    Step, Conditional, StartEnd, Io = range(4)

    def __init__(self, diagram_type, context_menu: QMenu, text_color: QColor,
                 item_color: QColor, font: QFont, position: QPointF, uuid=None,
                 name_text_item: DiagramTextItem=None, tag_text_item: DiagramTextItem=None, parent=None):
        super(DiagramNormalItem, self).__init__(parent)

        self.uuid = uuid if uuid is not None else SkFCBase.build_uuid()
        self.item_type: EnumItemType = EnumItemType.Normal
        self.diagram_type = diagram_type
        self.context_menu: QMenu = context_menu
        self.text_color: QColor = text_color
        self.item_color: QColor = item_color
        self.font: QFont = font
        self.arrows = []
        self.step: StepBase = None

        self.setBrush(item_color)
        self.setPos(position)

        self.name_text_item = DiagramTextItem(name_text_item.toPlainText() if name_text_item is not None else "hello",
                                              self.font, self.text_color, QPointF(-18, 18), parent=self)
        self.name_text_item.setTextInteractionFlags(Qt.TextEditable)

        self.tag_text_item = DiagramTextItem(tag_text_item.toPlainText() if tag_text_item is not None else "tag here",
                                             self.font, self.text_color, QPointF(-30, -12.5), parent=self)
        self.tag_text_item.setTextInteractionFlags(Qt.TextEditable)

        radius = ITEM_PORT_RADIUS
        self.port_bottom = DiagramSubItemPort(0 - radius, 15 - radius, 2 * radius, 2 * radius, EnumPortDir.BOTTOM, self)
        self.port_top = DiagramSubItemPort(0 - radius, -15 - radius, 2 * radius, 2 * radius, EnumPortDir.TOP, self)
        self.port_right = DiagramSubItemPort(50 - radius, 0 - radius, 2 * radius, 2 * radius, EnumPortDir.RIGHT, self)
        self.port_left = DiagramSubItemPort(-50 - radius, 0 - radius, 2 * radius, 2 * radius, EnumPortDir.LEFT, self)

        self.port_items = [self.port_top, self.port_bottom, self.port_right, self.port_left]

        self.setPolygon(DiagramNormalItem.create_item_polygon(self.diagram_type))
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)

        print(f"build diagram normal item {diagram_type}")

    @staticmethod
    def create_item_polygon(diagram_type):
        item_polygon = None
        if diagram_type == DiagramNormalItem.StartEnd:
            rect = QRectF(-50, -15, 100, 30)
            radius = 7.5
            path = QPainterPath()
            path.addRoundedRect(rect, radius, radius)
            item_polygon = path.toFillPolygon()
        elif diagram_type == DiagramNormalItem.Conditional:
            item_polygon = QPolygonF([
                    QPointF(-50, 0), QPointF(0, 15),
                    QPointF(50, 0), QPointF(0, -15),
                    QPointF(-50, 0)])
        elif diagram_type == DiagramNormalItem.Step:
            item_polygon = QPolygonF([
                    QPointF(-50, -15), QPointF(50, -15),
                    QPointF(50, 15), QPointF(-50, 15),
                    QPointF(-50, -15)])
        else:
            item_polygon = QPolygonF([
                    QPointF(-50, -15), QPointF(-35, 15),
                    QPointF(50, 15), QPointF(35, -15),
                    QPointF(-50, -15)])

        return item_polygon

    def get_port_item_by_direction(self, port_direction: EnumPortDir):
        for item in self.port_items:
            if item.direction == port_direction:
                return item

        return None

    def get_port_item_center_position_by_direction(self, port_direction: EnumPortDir):
        for item in self.port_items:
            if item.direction == port_direction:
                return item.sceneBoundingRect().center()

        return None

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

        print(f"normal item {self.uuid} append arrow item {new_arrow.uuid}")
        self.arrows.append(new_arrow)

    def mouse_move_redraw_arrows_path(self, event):
        # print(f"normal item {self.uuid} mouse move redraw arrow path")
        for arrow in self.arrows[:]:
            arrow.normal_item_move_redraw_path(self, event)

    # def image(self):
    #     pixmap = QPixmap(250, 250)
    #     pixmap.fill(Qt.transparent)
    #     painter = QPainter(pixmap)
    #     painter.setPen(QPen(Qt.black, 8))
    #     painter.translate(125, 125)
    #     painter.drawPolyline(self.myPolygon)
    #     return pixmap

    def contextMenuEvent(self, event):
        self.scene().clearSelection()
        self.setSelected(True)
        self.context_menu.exec_(event.screenPos())

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        # if event.buttons() == Qt.LeftButton:
        #     # offset = event.pos() - event.lastPos()
        #     # print(f"skfc item {self}; mouse event {event}")
        #     # self.redraw_arrows_path(event)
        #     pass

    def itemChange(self, change, value):
        # print(f"change:{change}; {value}")
        # if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
        #     # 当拖拽项的位置变化时，调整场景的大小以适应项的位置
        #     scene_rect = self.scene().itemsBoundingRect()
        #     self.scene().setSceneRect(scene_rect)

        return super().itemChange(change, value)

    def set_ports_visible(self, visible):
        self.port_top.setVisible(visible)
        self.port_bottom.setVisible(visible)
        self.port_right.setVisible(visible)
        self.port_left.setVisible(visible)

    # def calculate_distance(self, p1, p2):
    #     distance = math.sqrt((p2.x() - p1.x()) ** 2 + (p2.y() - p1.y()) ** 2)
    #     return int(distance)

    def closest_item_port_direction(self, point: QPointF) -> EnumPortDir:
        for item in self.port_items:
            # print((point - item.sceneBoundingRect().center()) .manhattanLength())
            if (point - item.sceneBoundingRect().center()).manhattanLength() <= ITEM_PORT_RADIUS*2:
                return item.direction

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

    def to_dict(self):
        obj_dict = {
            "uuid": self.uuid,
            "item_type": EnumItemType.enum_name(self.item_type),
            "diagram_type": self.diagram_type,
            "text_color": SkFCBase.color_encode(self.text_color),
            "item_color": SkFCBase.color_encode(self.brush().color()),
            "position": SkFCBase.position_encode(self.pos()),
            "font": SkFCBase.font_encode(self.font),
            "name_text_item": self.name_text_item.to_dict(),
            "tag_text_item": self.tag_text_item.to_dict()
        }

        return obj_dict

    @classmethod
    def from_dict(cls, obj_dict, context_menu: QMenu):
        diagram_type = obj_dict["diagram_type"]
        uuid = obj_dict["uuid"]
        text_color = QColor(SkFCBase.color_decode(obj_dict["text_color"]))
        item_color = QColor(SkFCBase.color_decode(obj_dict["item_color"]))
        position = SkFCBase.position_decode(obj_dict["position"])
        font = SkFCBase.font_decode(obj_dict["font"])

        name_text_item_dict = obj_dict["name_text_item"]
        tag_text_item_dict = obj_dict["tag_text_item"]

        name_text_item = DiagramTextItem.from_dict(name_text_item_dict, context_menu)
        tag_text_item = DiagramTextItem.from_dict(tag_text_item_dict, context_menu)

        diagram_normal_item = DiagramNormalItem(diagram_type=diagram_type, context_menu=context_menu, text_color=text_color,
                                                item_color=item_color, font=font, uuid=uuid, name_text_item=name_text_item,
                                                tag_text_item=tag_text_item, position=position)

        return diagram_normal_item


class DiagramItemGroup:
    def __init__(self, target_normal_item: DiagramNormalItem = None, target_item_port_direction: EnumPortDir = None):
        self.diagram_normal_item = target_normal_item
        self.diagram_item_port_direction = target_item_port_direction
