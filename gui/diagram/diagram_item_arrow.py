from enum import Enum

from PySide6.QtCore import QLineF, QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import QPainter, QPen, QColor, QPolygonF, QPainterPath, QBrush, QFont, QPainterPathStroker
from PySide6.QtWidgets import (QGraphicsPathItem, QGraphicsItem, QMenu, QGraphicsSceneMouseEvent, QGraphicsBlurEffect,
                               QGraphicsDropShadowEffect, QGraphicsColorizeEffect)
import math
from datetime import datetime

from gui.diagram.diagram_item import EnumPortDir, DiagramItemGroup, DiagramSubItemPort, DiagramItem

ARROW_MIN_SIZE = 15
ARROW_SIZE = 10
ARROW_ANGLE = 20
ARROW_WIDTH = 1.5
MANHANTAN_LENGTH = ARROW_SIZE/2


class DiagramArrowItem(QGraphicsPathItem):
    def __init__(self, start_point: QPointF, line_color, target_item_group: DiagramItemGroup = None,
                 context_menu: QMenu = None, parent=None, scene=None):
        super(DiagramArrowItem, self).__init__(parent, scene)

        print(f"build new arrow item with {target_item_group.diagram_item if target_item_group is not None else None};"
              f" {target_item_group.diagram_sub_item_port if target_item_group is not None else None}")
        self.start_point: QPointF = start_point
        self.end_point: QPointF = start_point
        self.line_color: QColor = line_color
        self.my_context_menu: QMenu = context_menu
        self.start_item: DiagramItem = target_item_group.diagram_item if target_item_group is not None else None
        self.start_sub_item_port: DiagramSubItemPort = target_item_group.diagram_sub_item_port if target_item_group is not None else None
        self.end_item: DiagramItem = None
        self.end_sub_item_port: DiagramSubItemPort = None
        self.path_points = []
        self.start_to_end_direction: bool = True
        self.arrow_head: QPolygonF = None
        self.old_start_item: DiagramItem = None
        self.old_end_item:DiagramItem = None

        self.pen = QPen(self.line_color, ARROW_WIDTH, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        self.setPen(self.pen)
        # self.setBrush(QBrush(QColor(self.line_color)))  # 设置箭头颜色为黑色

        # 设置可接收鼠标事件
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.LeftButton | Qt.RightButton)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        # self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)
        # self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

        if self.start_item is not None:
            # prevent default drag event
            self.start_item.setFlag(QGraphicsItem.ItemIsMovable, False)

            # update start point
            self.start_point = self.start_sub_item_port.sceneBoundingRect().center()

        print(f"init arrow item:{[self.start_point, self.end_point]}")

    def set_color(self, line_color):
        print(f"update line color:{line_color}")
        self.line_color = line_color
        self.pen = QPen(self.line_color, ARROW_WIDTH, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        self.setPen(self.pen)
        self.prepareGeometryChange()
        # self.update_path()
        self.update()

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        # super().paint(painter, option, widget)

        if self.isSelected():
            # 只绘制选择的直线
            # pen = painter.pen()
            pen = self.pen
            pen.setWidth(ARROW_WIDTH + 0.4)
            painter.setPen(pen)
            painter.drawPath(self.shape())
        else:
            # 绘制完整图形
            super().paint(painter, option, widget)

    def boundingRect(self):
        if self.isSelected():
            # 返回选择的直线的最小矩形边界
            return self.shape().boundingRect()
        else:
            # 返回完整图形的边界
            return super().boundingRect()

    # def itemChange(self, change, value):
    #     if change == QGraphicsItem.ItemSelectedChange:
    #         self.update()  # 更新图形以移除选中状态时的边界矩形显示
    #     elif change == QGraphicsItem.ItemPositionHasChanged:
    #         self.prepareGeometryChange()  # 准备几何变化，防止边界矩形显示
    #     return super().itemChange(change, value)

    def show_effect(self):
        # 为选中的直线添加阴影效果
        shadow_effect = QGraphicsDropShadowEffect()
        shadow_effect.setBlurRadius(10)
        shadow_effect.setColor(Qt.black)
        shadow_effect.setOffset(0)
        self.setGraphicsEffect(shadow_effect)

        # # 为选中的直线添加颜色效果
        # colorizeEffect = QGraphicsColorizeEffect()
        # colorizeEffect.setColor(Qt.red)
        # self.setGraphicsEffect(colorizeEffect)

    def hidden_effect(self):
        self.setGraphicsEffect(None)

    def shape(self):
        if self.isSelected():
            # 获取两条直线之间的路径
            stroke = QPainterPathStroker()
            # stroke.setWidth(2)  # 选中时的线宽
            path = stroke.createStroke(self.path())
            # path.addPath(self.path())  # 将两条路径合并为一个路径
            return path
        else:
            # 返回完整图形的形状
            return super().shape()

    def hoverEnterEvent(self, event):
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        super().hoverLeaveEvent(event)

    def hoverMoveEvent(self, event):
        local_pos = self.mapFromScene(event.scenePos())
        start_pos = self.path().pointAtPercent(0)
        end_pos = self.path().pointAtPercent(1)

        if (local_pos - start_pos).manhattanLength() < MANHANTAN_LENGTH:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        elif (local_pos - end_pos).manhattanLength() < MANHANTAN_LENGTH:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        # if event.button() == Qt.LeftButton:
        #     print("Left button pressed")

    def mouseReleaseEvent(self, event):
        # if event.button() == Qt.LeftButton:
        #     print("Left button released")
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        # if event.buttons() & Qt.LeftButton:
        #     print("Mouse moved with left button pressed")

    def contextMenuEvent(self, event):
        super().contextMenuEvent(event)
        # print("Right button pressed")
        self.scene().clearSelection()
        self.setSelected(True)
        self.my_context_menu.exec_(event.screenPos())

    def reselected_start_or_end_point(self, event):
        local_pos = self.mapFromScene(event.scenePos())
        start_pos = self.path().pointAtPercent(0)
        end_pos = self.path().pointAtPercent(1)

        self.old_start_item = self.start_item
        self.old_end_item = self.end_item

        if (local_pos - start_pos).manhattanLength() < MANHANTAN_LENGTH:
            self.start_to_end_direction = False
            return True
        elif (local_pos - end_pos).manhattanLength() < MANHANTAN_LENGTH:
            self.start_to_end_direction = True
            return True
        else:
            return False

    def remove_item_target_arrow(self):
        if self.start_item is not None:
            self.start_item.removeArrow(self)

        if self.end_item is not None:
            self.end_item.removeArrow(self)

    def delete_target_item(self, target_item: DiagramItem):
        if target_item == self.start_item:
            self.start_item = None
            self.start_sub_item_port = None
        elif target_item == self.end_item:
            self.end_item = None
            self.end_sub_item_port = None
        else:
            print(f"error no target item:{target_item}")

    def redraw_path(self, target_item: DiagramItem, event: QGraphicsSceneMouseEvent):
        print(f"redraw_path: {target_item}; event:{event.scenePos()}")
        if target_item == self.start_item and self.start_sub_item_port is not None:
            self.start_point = self.start_sub_item_port.sceneBoundingRect().center()

        if target_item == self.end_item and self.end_sub_item_port is not None:
            self.end_point = self.end_sub_item_port.sceneBoundingRect().center()

        self.prepareGeometryChange()
        self.update_path()

    def update_arrow_path(self, target_point: QPointF, target_item_group: DiagramItemGroup = None):
        # print(f"update move point:{target_point}; arrow path:{target_item_group}")
        update_path = True

        if self.start_to_end_direction is True:
            # if self.start_item is not None:
            #     self.start_item.setFlag(QGraphicsItem.ItemIsMovable, False)

            if target_item_group is None:
                self.end_item = None
                self.end_sub_item_port = None
            else:
                target_item = target_item_group.diagram_item
                target_sub_item_port: DiagramSubItemPort = target_item_group.diagram_sub_item_port

                if target_item is not None:
                    target_item.set_ports_visible(True)

                if target_item != self.start_item or \
                    (target_item == self.start_item and target_sub_item_port != self.start_sub_item_port):
                    self.end_item = target_item
                    self.end_sub_item_port = target_sub_item_port

                if self.end_sub_item_port is not None:
                    target_point = self.end_sub_item_port.sceneBoundingRect().center()

            if self.end_point == target_point:
                update_path = False
                # print("same end point not need update path")
            else:
                # print(f"update end point from: {self.end_point} to:{target_point}")
                self.end_point = target_point
        else:
            if target_item_group is None:
                self.start_item = None
                self.start_sub_item_port = None
            else:
                target_item = target_item_group.diagram_item
                target_sub_item_port: DiagramSubItemPort = target_item_group.diagram_sub_item_port

                if target_item is not None:
                    target_item.set_ports_visible(True)

                if target_item != self.end_item or \
                        (target_item == self.end_item and target_sub_item_port != self.end_sub_item_port):
                    self.start_item = target_item
                    self.start_sub_item_port = target_sub_item_port

                if self.start_sub_item_port is not None:
                    target_point = self.start_sub_item_port.sceneBoundingRect().center()

            if self.start_point == target_point:
                update_path = False
                # print("same end point not need update path")
            else:
                # print(f"update end point from: {self.end_point} to:{target_point}")
                self.start_point = target_point

        if update_path is True:
            self.prepareGeometryChange()
            self.update_path()

    def end_arrow_path(self, target_point: QPointF, target_item_group: DiagramItemGroup = None):
        # self.update_arrow_path(end_point, target_item_group)

        if self.start_item is not None:
            self.start_item.setFlag(QGraphicsItem.ItemIsMovable, True)

            self.start_item.addArrow(self)

        if self.old_start_item is not None and self.old_start_item != self.start_item:
            self.old_start_item.removeArrow(self)

        if self.end_item is not None:
            self.end_item.addArrow(self)

        if self.old_end_item is not None and self.old_end_item != self.end_item:
            self.old_end_item.removeArrow(self)

    def update_path(self):
        # 创建路径
        path = QPainterPath()

        self.path_points = self.calculate_path_points()
        if len(self.path_points) < 2:
            print(f"calculate path points error!!!{len(self.path_points)}")
        else:
            # print(f"moveTo:{self.path_points[0].x()}x{self.path_points[0].y()}")
            path.moveTo(self.path_points[0])
            for point in self.path_points[1:]:
                if point is not None:
                    # print(f"lineTo:{point}")
                    path.lineTo(point)

            # 计算2点的距离
            distance = calculate_distance(self.start_point.x(), self.start_point.y(), self.end_point.x(), self.end_point.y())
            # 当大于箭头长度的时候才开始添加箭头图像
            if distance >= ARROW_SIZE:
                # 将箭头形状添加到路径
                self.arrow_head = draw_arrow_head(self.path_points[-2], self.path_points[-1])
                path.addPolygon(self.arrow_head)

        self.setPath(path)

    def distance_too_short(self):
        distance = calculate_distance(self.start_point.x(), self.start_point.y(), self.end_point.x(), self.end_point.y())
        return distance < ARROW_SIZE

    def calculate_path_points(self) -> [QPointF]:
        points = []
        if self.start_item is not None and self.start_sub_item_port is not None and self.end_item is None:
            # print("calculate only start item path points")
            points = self.calculate_path_only_start_item_points()
        elif self.end_item is not None and self.end_sub_item_port is not None and self.start_item is None:
            # print("calculate only end item path points")
            points = self.calculate_path_only_end_item_points()
        elif self.start_item is not None and self.start_sub_item_port is not None and \
                self.end_item is not None and self.end_sub_item_port is not None:
            # print("calculate both have start and end item path points")
            points = self.calculate_path_both_two_item_points()
        else:
            # print("calculate both no start and end item path points")
            points = calculate_path_no_item_points(self.start_point, self.end_point)

        points = [x for x in points if x is not None]

        # remove same value point
        i = 0
        while i < len(points) - 1:
            if points[i] == points[i + 1] or points[i + 1] is None:
                del points[i + 1]
            else:
                i += 1

        return points

    def calculate_path_only_start_item_points(self):
        points = calculate_path_only_one_item_points(self.start_item, self.start_sub_item_port,
                                                     self.start_point, self.end_point)

        return points

    def calculate_path_only_end_item_points(self):
        points = calculate_path_only_one_item_points(self.end_item, self.end_sub_item_port,
                                                     self.end_point, self.start_point)

        return points[::-1]

    def calculate_path_both_two_item_points(self):
        points = []

        p1, p2, p3, p4, p5, p6, p7 = (None, None, None, None, None, None, None)
        start_item_scene_rect: QRectF = self.start_item.sceneBoundingRect()
        end_item_scene_rect: QRectF = self.end_item.sceneBoundingRect()
        start_port_direction = self.start_sub_item_port.direction
        end_port_direction = self.end_sub_item_port.direction
        last_point = self.end_point
        p1 = self.start_point

        p2 = build_io_part_line(p1, start_port_direction)
        second_to_last_point = build_io_part_line(last_point, end_port_direction)

        enlarge_start_item_scene_rect = enlarge_rect(start_item_scene_rect, ARROW_MIN_SIZE)
        enlarge_end_item_scene_rect = enlarge_rect(end_item_scene_rect, ARROW_MIN_SIZE)

        full_size_rect: QRectF = include_two_items_rect(start_item_scene_rect, end_item_scene_rect, ARROW_MIN_SIZE)
        shortest_line_x = p2.x()
        shortest_line_y = p2.y()
        total_distance = 0
        min_total_distance = float('inf')

        # 同向 180°
        if (start_port_direction == EnumPortDir.RIGHT or start_port_direction == EnumPortDir.LEFT) and \
                (end_port_direction == EnumPortDir.RIGHT or end_port_direction == EnumPortDir.LEFT):
            print(f"calculate horizontal start port dir:{start_port_direction}; end port dir:{end_port_direction}")
            start_to_end_horizontal_distance = abs(p2.x() - second_to_last_point.x())
            for y_pos in range(int(full_size_rect.top()), int(full_size_rect.bottom()) + 1):
                start_vertical_distance = abs(y_pos - p2.y())
                end_vertical_distance = abs(y_pos - second_to_last_point.y())
                horizontal_start_point = QPointF(p2.x(), y_pos)
                horizontal_end_point = QPointF(second_to_last_point.x(), y_pos)
                line = QLineF(horizontal_start_point, horizontal_end_point)
                intersect_start_item = is_line_intersect_rect(line, enlarge_start_item_scene_rect)
                intersect_end_item = is_line_intersect_rect(line, enlarge_end_item_scene_rect)
                # print(f"y_pos:{y_pos}; start intersect:{intersect_start_item}; end intersect:{intersect_end_item}")
                if intersect_start_item is False and intersect_end_item is False:
                    total_distance = start_to_end_horizontal_distance + start_vertical_distance + end_vertical_distance
                    if total_distance < min_total_distance:
                        min_total_distance = total_distance
                        shortest_line_y = y_pos
                    elif total_distance == min_total_distance:
                        # 替换为离出发点最近的点
                        if y_pos == p1.y() or y_pos == last_point.y():
                            shortest_line_y = y_pos
                        # elif abs(y_pos - p1.y()) < abs(shortest_line_y - p1.y()):
                        #     shortest_line_y = y_pos

            print(f"min_total_distance:{min_total_distance}; shortest_line_y:{shortest_line_y}")

            p3 = QPointF(p2.x(), shortest_line_y)
            p4 = QPointF(second_to_last_point.x(), shortest_line_y)
            p5 = second_to_last_point
            p6 = last_point

            points.extend([p1, p2, p3, p4, p5, p6])
        # 同向 180°
        elif (start_port_direction == EnumPortDir.TOP or start_port_direction == EnumPortDir.BOTTOM) and \
                (end_port_direction == EnumPortDir.TOP or end_port_direction == EnumPortDir.BOTTOM):
            print(f"calculate vertical start port dir:{start_port_direction}; end port dir:{end_port_direction}")
            start_to_end_vertical_distance = abs(p2.y() - second_to_last_point.y())
            for x_pos in range(int(full_size_rect.left()), int(full_size_rect.right()) + 1):
                start_horizontal_distance = abs(x_pos - p2.x())
                end_horizontal_distance = abs(x_pos - second_to_last_point.x())
                vertical_start_point = QPointF(x_pos, p2.y())
                vertical_end_point = QPointF(x_pos, second_to_last_point.y())
                line = QLineF(vertical_start_point, vertical_end_point)
                intersect_start_item = is_line_intersect_rect(line, enlarge_start_item_scene_rect)
                intersect_end_item = is_line_intersect_rect(line, enlarge_end_item_scene_rect)
                # print(f"x_pos:{x_pos}; start intersect:{intersect_start_item}; end intersect:{intersect_end_item}")
                if intersect_start_item is False and intersect_end_item is False:
                    total_distance = start_to_end_vertical_distance + start_horizontal_distance + end_horizontal_distance
                    if total_distance < min_total_distance:
                        min_total_distance = total_distance
                        shortest_line_x = x_pos
                    elif total_distance == min_total_distance:
                        # 替换为离出发点最近的点
                        if x_pos == p1.x() or x_pos == last_point.x():
                            shortest_line_x = x_pos
                        # elif abs(x_pos - p1.x()) < abs(shortest_line_x - p1.x()):
                        #     shortest_line_x = x_pos

            print(f"min_total_distance:{min_total_distance}; shortest_line_x:{shortest_line_x}")

            p3 = QPointF(shortest_line_x, p2.y())
            p4 = QPointF(shortest_line_x, second_to_last_point.y())
            p5 = second_to_last_point
            p6 = last_point

            points.extend([p1, p2, p3, p4, p5, p6])
        # 夹角 90°
        else:
            print(f"calculate two items is 90° start port dir:{start_port_direction}; end port dir:{end_port_direction}")
            start_item_direction_range = item_port_direction_range(p2, start_port_direction, full_size_rect)
            end_item_direction_range = item_port_direction_range(second_to_last_point, end_port_direction, full_size_rect)
            third_point, third_to_last_point, intersect_point = (None, None, None)
            intersect_position, third_position, third_to_last_position = \
                ({'x': 0, 'y': 0}, {'x': 0, 'y': 0}, {'x': 0, 'y': 0})
            start_horizontal_distance, start_vertical_distance, end_horizontal_distance, end_vertical_distance = (
                0, 0, 0, 0)
            intersect_line = QLineF(QPointF(0, 0), QPointF(0, 0))

            enlarge_start_item_edge_lines = decode_four_edge_lines(enlarge_start_item_scene_rect)
            enlarge_end_item_edge_lines = decode_four_edge_lines(enlarge_end_item_scene_rect)

            print(f"start_item_direction_range size:{len(start_item_direction_range)}")
            print(f"end_item_direction_range size:{len(end_item_direction_range)}")

            step_1 = int(datetime.now().timestamp() * 1000000)
            for start_dir_pos in start_item_direction_range:
                # step_2 = int(datetime.now().timestamp() * 1000000)
                for end_dir_pos in end_item_direction_range:
                    # print(f"start_dir_pos:{start_dir_pos};end_dir_pos:{end_dir_pos}")
                    start_horizontal_distance, start_vertical_distance, end_horizontal_distance, end_vertical_distance = (0, 0, 0, 0)
                    third_position['x'] = p2.x()
                    third_position['y'] = p2.y()
                    third_to_last_position['x'] = second_to_last_point.x()
                    third_to_last_position['y'] = second_to_last_point.y()

                    # 判断是否和p2 点重叠
                    if start_port_direction == EnumPortDir.LEFT or start_port_direction == EnumPortDir.RIGHT:
                        intersect_position['x'] = start_dir_pos
                        intersect_position['y'] = end_dir_pos

                        if intersect_position['x'] != p2.x():
                            third_position['x'] = intersect_position['x']
                            third_position['y'] = p2.y()

                            start_horizontal_distance = abs(third_position['x'] - p2.x())

                        # 判断是否和second_to_last_point 点重叠
                        if intersect_position['y'] != second_to_last_point.y():
                            third_to_last_position['x'] = second_to_last_point.x()
                            third_to_last_position['y'] = intersect_position['y']
                            end_vertical_distance = abs(second_to_last_point.y() - third_to_last_position['y'])

                        start_vertical_distance = abs(third_position['y'] - intersect_position['y'])
                        end_horizontal_distance = abs(intersect_position['x'] - third_to_last_position['x'])
                    else:
                        # 判断是否和p2 点重叠
                        intersect_position['x'] = end_dir_pos
                        intersect_position['y'] = start_dir_pos

                        if intersect_position['y'] != p2.y():
                            third_position['x'] = p2.x()
                            third_position['y'] = intersect_position['y']

                            start_vertical_distance = abs(p2.y() - third_position['y'])

                        # 判断是否和second_to_last_point 点重叠
                        if intersect_position['x'] != second_to_last_point.x():
                            third_to_last_position['x'] = intersect_position['x']
                            third_to_last_position['y'] = second_to_last_point.y()

                            end_horizontal_distance = abs(second_to_last_point.x() - third_to_last_position['x'])

                        start_horizontal_distance = abs(third_position['x'] - intersect_position['x'])
                        end_vertical_distance = abs(intersect_position['y'] - third_to_last_position['y'])

                    total_distance = (start_horizontal_distance + start_vertical_distance +
                                      end_horizontal_distance + end_vertical_distance)

                    # print(f"total_distance:{total_distance};min_total_distance:{min_total_distance}")
                    if total_distance <= min_total_distance:
                        update_path_points = False
                        if total_distance < min_total_distance:
                            update_path_points = True
                        elif total_distance == min_total_distance:
                            if start_port_direction == EnumPortDir.LEFT or start_port_direction == EnumPortDir.RIGHT:
                                if intersect_position['y'] == p1.y() or intersect_position['x'] == last_point.x():
                                    update_path_points = True
                            else:
                                if intersect_position['x'] == p1.x() or intersect_position['y'] == last_point.y():
                                    update_path_points = True

                        if update_path_points is True:
                            intersect_point = QPointF(intersect_position['x'], intersect_position['y'])
                            third_point = QPointF(third_position['x'], third_position['y'])
                            third_to_last_point = QPointF(third_to_last_position['x'], third_to_last_position['y'])

                            intersect_line.setPoints(p2, third_point)
                            if is_line_intersect_four_edge(intersect_line, enlarge_end_item_edge_lines):
                                print(f"intersect break#1:{intersect_line}")
                                continue

                            intersect_line.setPoints(second_to_last_point, third_to_last_point)
                            if is_line_intersect_four_edge(intersect_line, enlarge_start_item_edge_lines):
                                print(f"intersect break#2:{intersect_line}")
                                continue

                            intersect_line.setPoints(third_point, intersect_point)
                            if is_line_intersect_four_edge(intersect_line, enlarge_end_item_edge_lines):
                                print(f"intersect break#3:{intersect_line}")
                                continue

                            intersect_line.setPoints(third_to_last_point, intersect_point)
                            if is_line_intersect_four_edge(intersect_line, enlarge_start_item_edge_lines):
                                print(f"intersect break#4:{intersect_line}")
                                continue

                            p3 = third_point
                            p4 = intersect_point
                            p5 = third_to_last_point
                            p6 = second_to_last_point
                            p7 = last_point

                            min_total_distance = total_distance
                            # print(f"update total_distance:{total_distance}; intersect_point:{intersect_point}")

                # now = int(datetime.now().timestamp() * 1000000)
                # print(f"step#2 count:{start_dir_pos}; use time:{now - step_2}")

            now = int(datetime.now().timestamp() * 1000000)
            print(f"step#1 time:{now - step_1}")

            points.extend([p1, p2, p3, p4, p4, p5, p6, p7])

        return points


# 2点之间没有任何节点有交集的case
def calculate_path_no_item_points(start_point: QPointF, end_point: QPointF):
    points = []

    p1 = start_point
    last_point = end_point

    direction = two_point_direction(p1, last_point)
    if direction == EnumDirection.COINCIDE:
        print("path point coincide")
        return points

    middle_point_x = (p1.x() + last_point.x()) / 2.0
    middle_point_y = (p1.y() + last_point.y()) / 2.0
    p2 = QPointF(middle_point_x, p1.y())
    p3 = QPointF(middle_point_x, last_point.y())
    p4 = last_point
    points.extend([p1, p2, p3, p4])

    return points


def calculate_path_only_one_item_points(item: DiagramItem, sub_item_port: DiagramSubItemPort,
                                        start_point: QPointF, end_point: QPointF):
    points = []
    p1, p2, p3, p4, p5 = (None, None, None, None, None)
    item_scene_rect: QRectF = item.sceneBoundingRect()
    port_direction = sub_item_port.direction
    last_point = end_point
    p1 = start_point

    p2 = build_io_part_line(p1, port_direction)
    sides_position = points_with_sides_position(item_scene_rect, p2, last_point)
    # print(f"sides_position:{sides_position}; port direction:{port_direction}")

    if sides_position == EnumSidesPosition.SAME:
        if port_direction == EnumPortDir.RIGHT:
            if last_point.x() >= p2.x():
                p3 = QPointF(last_point.x(), p2.y())
            else:
                p3 = QPointF(p2.x(), last_point.y())
        elif port_direction == EnumPortDir.LEFT:
            if last_point.x() <= p2.x():
                p3 = QPointF(last_point.x(), p2.y())
            else:
                p3 = QPointF(p2.x(), last_point.y())
        elif port_direction == EnumPortDir.TOP:
            if last_point.y() <= p2.y():
                p3 = QPointF(p2.x(), last_point.y())
            else:
                p3 = QPointF(last_point.x(), p2.y())
        elif port_direction == EnumPortDir.BOTTOM:
            if last_point.y() >= p2.y():
                p3 = QPointF(p2.x(), last_point.y())
            else:
                p3 = QPointF(last_point.x(), p2.y())
        p4 = last_point
        points.extend([p1, p2, p3, p4])
    elif sides_position == EnumSidesPosition.BESIDE:
        if port_direction == EnumPortDir.RIGHT:
            p3 = QPointF(p2.x(), last_point.y())
        elif port_direction == EnumPortDir.LEFT:
            p3 = QPointF(p2.x(), last_point.y())
        elif port_direction == EnumPortDir.TOP:
            p3 = QPointF(last_point.x(), p2.y())
        elif port_direction == EnumPortDir.BOTTOM:
            p3 = QPointF(last_point.x(), p2.y())
        p4 = last_point
        points.extend([p1, p2, p3, p4])
    elif sides_position == EnumSidesPosition.OPPOSITE:
        if port_direction == EnumPortDir.RIGHT:
            if (last_point.y() < item_scene_rect.topRight().y() or
                    last_point.y() > item_scene_rect.bottomRight().y()):
                p3 = QPointF(p2.x(), last_point.y())
            else:
                if p1.y() >= last_point.y() >= item_scene_rect.topRight().y():
                    p3 = QPointF(p2.x(), item_scene_rect.topRight().y() - ARROW_MIN_SIZE)
                    p4 = QPointF(last_point.x(), p3.y())
                else:
                    p3 = QPointF(p2.x(), item_scene_rect.bottomRight().y() + ARROW_MIN_SIZE)
                    p4 = QPointF(last_point.x(), p3.y())
        elif port_direction == EnumPortDir.LEFT:
            if (last_point.y() < item_scene_rect.topLeft().y() or
                    last_point.y() > item_scene_rect.bottomLeft().y()):
                p3 = QPointF(p2.x(), last_point.y())
            else:
                if p1.y() >= last_point.y() >= item_scene_rect.topLeft().y():
                    p3 = QPointF(p2.x(), item_scene_rect.topLeft().y() - ARROW_MIN_SIZE)
                    p4 = QPointF(last_point.x(), p3.y())
                else:
                    p3 = QPointF(p2.x(), item_scene_rect.bottomLeft().y() + ARROW_MIN_SIZE)
                    p4 = QPointF(last_point.x(), p3.y())
        elif port_direction == EnumPortDir.TOP:
            if (last_point.x() < item_scene_rect.topLeft().x() or
                    last_point.x() > item_scene_rect.topRight().x()):
                p3 = QPointF(last_point.x(), p2.y())
            else:
                if item_scene_rect.topLeft().x() <= last_point.x() <= p1.x():
                    p3 = QPointF(item_scene_rect.topLeft().x() - ARROW_MIN_SIZE, p2.y())
                    p4 = QPointF(p3.x(), last_point.y())
                else:
                    p3 = QPointF(item_scene_rect.topRight().x() + ARROW_MIN_SIZE, p2.y())
                    p4 = QPointF(p3.x(), last_point.y())
        elif port_direction == EnumPortDir.BOTTOM:
            if (last_point.x() < item_scene_rect.bottomLeft().x() or
                    last_point.x() > item_scene_rect.bottomRight().x()):
                p3 = QPointF(last_point.x(), p2.y())
            else:
                if item_scene_rect.bottomLeft().x() <= last_point.x() <= p1.x():
                    p3 = QPointF(item_scene_rect.bottomLeft().x() - ARROW_MIN_SIZE, p2.y())
                    p4 = QPointF(p3.x(), last_point.y())
                else:
                    p3 = QPointF(item_scene_rect.bottomRight().x() + ARROW_MIN_SIZE, p2.y())
                    p4 = QPointF(p3.x(), last_point.y())
        p5 = last_point
        points.extend([p1, p2, p3, p4, p5])

    return points


def calculate_distance(x1, y1, x2, y2):
    distance = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
    return int(distance)


def draw_arrow_head(start: QPointF, end: QPointF) -> QPolygonF:
    # print("draw arrow head")

    # 计算直线的斜率
    dx = end.x() - start.x()
    dy = end.y() - start.y()
    slope = math.atan2(dy, dx)

    # 创建箭头形状
    arrow_polygon = QPolygonF()

    start_point = QPointF(end.x(), end.y())

    # 添加箭头, 计算箭头顶点坐标
    arrow_polygon.append(start_point)
    arrow_polygon.append(QPointF(end.x() - ARROW_SIZE * math.cos(slope + math.radians(ARROW_ANGLE)),
                                 end.y() - ARROW_SIZE * math.sin(slope + math.radians(ARROW_ANGLE))))
    arrow_polygon.append(QPointF(end.x() - ARROW_SIZE * math.cos(slope - math.radians(ARROW_ANGLE)),
                                 end.y() - ARROW_SIZE * math.sin(slope - math.radians(ARROW_ANGLE))))
    arrow_polygon.append(start_point)

    return arrow_polygon


class EnumDirection(Enum):
    COINCIDE = 0
    ABOVE = 1
    BELOW = 2
    LEFT = 3
    RIGHT = 4
    TOP_LEFT = 13
    TOP_RIGHT = 14
    BOTTOM_LEFT = 23
    BOTTOM_RIGHT = 24


class EnumSidesPosition(Enum):
    BESIDE = 0
    SAME = 1
    OPPOSITE = 2


def two_point_direction(start_point: QPointF, end_point: QPointF):
    diff = end_point - start_point

    if diff.x() > 0 and diff.y() < 0:
        # print("end point is in the top-right direction of start point")
        return EnumDirection.TOP_RIGHT
    elif diff.x() < 0 and diff.y() < 0:
        # print("end point is in the top-left direction of start point")
        return EnumDirection.TOP_LEFT
    elif diff.x() < 0 and diff.y() > 0:
        # print("end point is in the bottom-left direction of start point")
        return EnumDirection.BOTTOM_LEFT
    elif diff.x() > 0 and diff.y() > 0:
        # print("end point is in the bottom-right direction of start point")
        return EnumDirection.BOTTOM_RIGHT
    elif diff.x() == 0 and diff.y() < 0:
        # print("end point is in the above direction of start point")
        return EnumDirection.ABOVE
    elif diff.x() == 0 and diff.y() > 0:
        # print("end point is in the below direction of start point")
        return EnumDirection.BELOW
    elif diff.x() > 0 and diff.y() == 0:
        # print("end point is in the right direction of start point")
        return EnumDirection.RIGHT
    elif diff.x() < 0 and diff.y() == 0:
        # print("end point is in the left direction of start point")
        return EnumDirection.LEFT
    else:
        # print("end point coincides with start point")
        return EnumDirection.COINCIDE


def enlarge_rect(orig_rect: QRectF, length_increment) -> QRectF:
    if orig_rect is None:
        return None

    center = orig_rect.center()

    # 计算新的矩形的宽度和高度
    new_width = orig_rect.width() + length_increment
    new_height = orig_rect.height() + length_increment

    # 计算新的矩形的左上角坐标
    new_left = center.x() - 0.5 * new_width
    new_top = center.y() - 0.5 * new_height

    # 创建新的放大后的矩形
    new_rect = QRectF(new_left, new_top, new_width, new_height)
    # print(f"enlarge orig rect:{orig_rect};new rect:{new_rect}")

    return new_rect


def is_two_points_intersect_rect(point1: QPointF, point2: QPointF, rect: QRectF) -> bool:
    if point1 is not None and point2 is not None:
        return is_line_intersect_rect(QLineF(point1, point2), rect)

    return False


def decode_four_edge_lines(rect: QRectF) -> ():
    top_line = QLineF(rect.topLeft(), rect.topRight())
    bottom_line = QLineF(rect.bottomLeft(), rect.bottomRight())
    left_line = QLineF(rect.topLeft(), rect.bottomLeft())
    right_line = QLineF(rect.topRight(), rect.bottomRight())

    return top_line, bottom_line, left_line, right_line


def is_line_intersect_rect(line: QLineF, rect: QRectF) -> bool:
    if line is None or line.length() == 0:
        return False

    # Check if the line segment intersects with any of the four sides of the rectangle
    top_line = QLineF(rect.topLeft(), rect.topRight())
    bottom_line = QLineF(rect.bottomLeft(), rect.bottomRight())
    left_line = QLineF(rect.topLeft(), rect.bottomLeft())
    right_line = QLineF(rect.topRight(), rect.bottomRight())

    return is_line_intersect_four_edge(line, (top_line, bottom_line, left_line, right_line))


def is_line_intersect_four_edge(line: QLineF, edge_lines: ()) -> bool:
    if line is None or line.length() == 0:
        return False

    # Check if the line segment intersects with any of the four sides of the rectangle
    top_line, bottom_line, left_line, right_line = edge_lines
    check_edge_lines = []
    # vertical
    if line.dx() == 0:
        if left_line.x1() < line.p1().x() < right_line.x1():
            check_edge_lines.extend([top_line, bottom_line])
    # horizontal
    elif line.dy() == 0:
        if top_line.y1() < line.p1().y() < bottom_line.y1():
            check_edge_lines.extend([left_line, right_line])
    else:
        check_edge_lines.extend([top_line, bottom_line, left_line, right_line])

    for edge in check_edge_lines:
        result, point = line.intersects(edge)
        if result == QLineF.IntersectionType.BoundedIntersection:
            return True

    return False


def points_with_sides_position(rect: QRectF, point1: QPointF, point2: QPointF):
    # print(f"{point1.x()};{rect.right()};{point2.x()};{rect.left()}")
    position = EnumSidesPosition.BESIDE
    if (point1.x() < rect.left() and point2.x() > rect.right()) or \
            (point1.x() > rect.right() and point2.x() < rect.left()) or \
            (point1.y() < rect.top() and point2.y() > rect.bottom()) or \
            (point1.y() > rect.bottom() and point2.y() < rect.top()):
        position = EnumSidesPosition.OPPOSITE
    elif (point1.x() < rect.left() and point2.x() < rect.left()) or \
            (point1.x() > rect.right() and point2.x() > rect.right()) or \
            (point1.y() < rect.top() and point2.y() < rect.top()) or \
            (point1.y() > rect.bottom() and point2.y() > rect.bottom()):
        position = EnumSidesPosition.SAME

    return position


def points_relative_two_items_position(rect1: QRectF, rect2: QRectF, point1: QPointF, point2: QPointF):
    position = EnumSidesPosition.BESIDE
    if ((point1.x() < rect1.left() and point1.x() < rect2.left()) and
        (point2.x() > rect1.right() and point2.x() > rect2.right())) or \
            ((point2.x() < rect1.left() and point2.x() < rect2.left()) and
             (point1.x() > rect1.right() and point1.x() > rect2.right())) or \
            ((point1.y() < rect1.top() and point1.y() < rect2.top()) and
             (point2.y() > rect1.bottom() and point2.y() > rect2.bottom())) or \
            ((point2.y() < rect1.top() and point2.y() < rect2.top()) and
             (point1.y() > rect1.bottom() and point1.y() > rect2.bottom())):
        position = EnumSidesPosition.OPPOSITE
    elif ((rect1.right() < point1.x() < rect2.left()) and
          (rect1.right() < point2.x() < rect2.left())) or \
            ((rect2.right() < point1.x() < rect1.left()) and
             (rect2.right() < point2.x() < rect1.left())) or \
            ((rect1.bottom() < point1.y() < rect2.top()) and
             (rect1.bottom() < point2.y() < rect2.top())) or \
            ((rect2.bottom() < point1.y() < rect1.top()) and
             (rect2.bottom() < point2.y() < rect1.top())):
        position = EnumSidesPosition.SAME

    return position


def build_io_part_line(p1, direction) -> QPointF:
    # print(f"build_io_part_line direction:{direction}")
    if direction == EnumPortDir.RIGHT:
        return QPointF(int(p1.x() + ARROW_MIN_SIZE), p1.y())
    elif direction == EnumPortDir.LEFT:
        return QPointF(int(p1.x() - ARROW_MIN_SIZE), p1.y())
    elif direction == EnumPortDir.TOP:
        return QPointF(p1.x(), int(p1.y() - ARROW_MIN_SIZE))
    elif direction == EnumPortDir.BOTTOM:
        return QPointF(p1.x(), int(p1.y() + ARROW_MIN_SIZE))


def two_rect_no_overlap_vertical(rect1: QRectF, rect2: QRectF):
    no_overlap = (rect1.top() - ARROW_MIN_SIZE > rect2.bottom() + ARROW_MIN_SIZE) or \
                 (rect1.bottom() + ARROW_MIN_SIZE < rect2.top() - ARROW_MIN_SIZE)

    return no_overlap


def two_rect_no_overlap_horizontal(rect1: QRectF, rect2: QRectF):
    no_overlap = (rect1.right() + ARROW_MIN_SIZE < rect2.left() - ARROW_MIN_SIZE) or \
                 (rect1.left() - ARROW_MIN_SIZE > rect2.right() + ARROW_MIN_SIZE)

    return no_overlap


def include_two_items_rect(start_item_rect: QRectF, end_item_rect: QRectF, enlarge_size) -> QRectF:
    max_right_x = max(start_item_rect.right(), end_item_rect.right()) + enlarge_size
    min_left_x = min(start_item_rect.left(), end_item_rect.left()) - enlarge_size
    max_bottom_y = max(start_item_rect.bottom(), end_item_rect.bottom()) + enlarge_size
    min_top_y = min(start_item_rect.top(), end_item_rect.top()) - enlarge_size

    # left: float, top: float, width: float, height: float
    return QRectF(min_left_x, min_top_y, abs(max_right_x - min_left_x), abs(max_bottom_y - min_top_y))


def item_port_direction_range(point: QPointF, direction, rect: QRectF) -> []:
    step_range = []

    # print(f"point:{point};direction:{direction};rect:{rect}")
    if direction == EnumPortDir.RIGHT:
        step_range = [x for x in range(int(point.x()), int(rect.right()) + 1)]
    elif direction == EnumPortDir.LEFT:
        # step_range = [x for x in range(int(rect.left()), int(point.x()) + 1)]
        step_range = [x for x in range(int(point.x()), int(rect.left()) - 1, -1)]
    elif direction == EnumPortDir.TOP:
        # step_range = [y for y in range(int(rect.top()), int(point.y()) + 1)]
        step_range = [y for y in range(int(point.y()), int(rect.top()) - 1, -1)]
    elif direction == EnumPortDir.BOTTOM:
        step_range = [y for y in range(int(point.y()), int(rect.bottom()) + 1)]

    return step_range
