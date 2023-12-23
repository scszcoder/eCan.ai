from typing import Optional

from PySide6.QtCore import (Signal, QPointF, Qt)
from PySide6.QtGui import (QFont, QColor)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene, QMenu
from gui.skfc.diagram_item_normal import DiagramNormalItem, DiagramSubItemPort, DiagramItemGroup
from gui.skfc.diagram_item_text import DiagramTextItem
from gui.skfc.diagram_item_arrow import DiagramArrowItem
from gui.skfc.skfc_base import EnumItemType
from skill.steps.enum_step_type import EnumStepType
from skill.steps.step_goto import StepGoto
from skill.steps.step_header import StepHeader
from skill.steps.step_stub import EnumStubName, StepStub


class SkFCScene(QGraphicsScene):
    InsertItem, InsertLine, InsertText, MoveItem, SetTxtBold, SetTxtItalic, SetTxtUnderline = range(7)

    itemInserted = Signal(DiagramNormalItem)

    textInserted = Signal(DiagramTextItem)

    arrowInserted = Signal(DiagramArrowItem)

    itemSelected = Signal(QGraphicsItem)

    def __init__(self, item_menu, parent=None):
        super(SkFCScene, self).__init__(parent)

        self.myItemMenu: QMenu = item_menu
        self.parent = parent
        self.myMode = self.MoveItem
        self.myItemType: DiagramNormalItem = DiagramNormalItem.Step
        self.selected_item = None
        self.textItem: DiagramTextItem = None
        self.myItemColor: QColor = QColor(Qt.white)
        self.myTextColor: QColor = QColor(Qt.black)
        self.myLineColor: QColor = QColor(Qt.black)
        self.myFont: QFont = QFont("Times New Roman", 14)
        self.gridSize = 5

        self.diagram_item_map_stepN = {}

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
        if self.isItemChange(DiagramNormalItem):
            item: DiagramNormalItem = self.selectedItems()[0]
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

    # def editorLostFocus(self, item):
    #     cursor = item.textCursor()
    #     cursor.clearSelection()
    #     item.setTextCursor(cursor)
    #
    #     if item.toPlainText():
    #         self.removeItem(item)
    #         item.deleteLater()

    def mousePressEvent(self, mouseEvent):
        # super(SkFCScene, self).mousePressEvent(mouseEvent)
        if mouseEvent.button() != Qt.LeftButton:
            return

        if self.myMode == self.InsertItem:
            print("inserting a normal item...")
            item = DiagramNormalItem(diagram_type=self.myItemType, context_menu=self.myItemMenu, text_color=self.myTextColor,
                                     item_color=self.myItemColor, font=self.myFont, position=mouseEvent.scenePos())
            self.add_diagram_item(item)
            self.itemInserted.emit(item)
            self.selected_item = item
        elif self.myMode == self.InsertLine:
            print("inserting a line...")
            if self.isItemChange(DiagramArrowItem):
                line: DiagramArrowItem = self.selectedItems()[0]
                if line.prepare_dragging(mouseEvent) is True:
                    self.selected_item = line
                else:
                    print("selected existed line but not start or end point so can not be drag #1")
            else:
                target_item_group = self.query_target_event_items(mouseEvent.scenePos())
                # 当点击对应的item时候，需要要有选择到 port才能开始画线
                if target_item_group is None or target_item_group.diagram_item_port_direction is not None:
                    item = DiagramArrowItem(start_point=mouseEvent.scenePos(), line_color=self.myLineColor,
                                            context_menu=self.myItemMenu, target_item_group=target_item_group)

                    self.add_diagram_item(item)
                    self.selected_item = item
                elif target_item_group is not None:
                    self.selected_item = target_item_group.diagram_normal_item
                else:
                    pass
        elif self.myMode == self.InsertText:
            print("inserting a text...")
            item = DiagramTextItem(plain_text="hello", font=self.myFont, color=self.myTextColor,
                                   position=mouseEvent.scenePos(), sub_item=False, context_menu=self.myItemMenu)
            self.add_diagram_item(item)
            self.textInserted.emit(item)
            self.selected_item = item
        elif self.myMode == self.MoveItem:
            if self.isItemChange(DiagramArrowItem):
                line: DiagramArrowItem = self.selectedItems()[0]
                if line.prepare_dragging(mouseEvent) is True:
                    self.selected_item = line
                else:
                    print("selected existed line but not start or end point so can not be drag #2")
            else:
                if len(self.selectedItems()) > 0:
                    self.selected_item = self.selectedItems()[0]

        if self.selected_item is not None:
            if isinstance(self.selected_item, DiagramNormalItem):
                self.parent.skfc_infobox.show_diagram_item_step_attrs(self.selected_item)

        super(SkFCScene, self).mousePressEvent(mouseEvent)

    def mouseMoveEvent(self, mouseEvent):
        # super().mouseMoveEvent(mouseEvent)
        if isinstance(self.selected_item, DiagramNormalItem):
            # diagram_item: DiagramNormalItem = self.selectedItems()[0]
            self.selected_item.mouse_move_redraw_arrows_path(mouseEvent)
            super().mouseMoveEvent(mouseEvent)
            # print(f"moving normal item {self.selected_item}")
        elif isinstance(self.selected_item, DiagramArrowItem):
            target_item_group = self.query_target_event_items(mouseEvent.scenePos())
            self.selected_item.mouse_move_handler(mouseEvent.scenePos(), target_item_group)
            # print(f"moving arrow item {self.selected_item}")
        else:
            super().mouseMoveEvent(mouseEvent)

        # super().mouseMoveEvent(mouseEvent)

    def mouseReleaseEvent(self, mouseEvent):
        # super(SkFCScene, self).mouseReleaseEvent(mouseEvent)
        if self.selected_item is not None:
            if isinstance(self.selected_item, DiagramArrowItem):
                line: DiagramArrowItem = self.selected_item
                target_item_group = self.query_target_event_items(mouseEvent.scenePos())
                line.mouse_release_handler(mouseEvent.scenePos(), target_item_group)
                if line.distance_too_short():
                    self.removeItem(line)
                    print("line distance is too short should removed from scene")
                else:
                    self.arrowInserted.emit(line)
            elif isinstance(self.selected_item, DiagramNormalItem):
                # print(f"mouse release event to {self.selected_item.uuid}")
                self.selected_item.mouse_move_redraw_arrows_path(mouseEvent)
                super().mouseMoveEvent(mouseEvent)
        else:
            print("mouse release handle but selected item is none")

        self.selected_item = None
        super(SkFCScene, self).mouseReleaseEvent(mouseEvent)

    def query_target_event_items(self, point: QPointF):
        target_item_group: DiagramItemGroup = None

        items = self.items(point)
        for item in items:
            if isinstance(item, DiagramNormalItem):
                target_item_group = DiagramItemGroup(item, item.closest_item_port_direction(point))
            elif isinstance(item, DiagramSubItemPort):
                target_item_group = DiagramItemGroup(item.parent, item.direction)

        return target_item_group

    def isItemChange(self, type):
        # print(f"selected item change type {type}")
        for item in self.selectedItems():
            if isinstance(item, type):
                print(f"selected item {item} same type {type}")
                return True
        return False

    def add_diagram_item(self, item):
        self.addItem(item)

    def remove_diagram_item(self, item):
        print(f"remove item {item} from scene")

        if isinstance(item, DiagramNormalItem):
            item.remove_arrows_items()
        elif isinstance(item, DiagramArrowItem):
            item.remove_item_target_arrow()
        elif isinstance(item, DiagramTextItem):
            pass

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
    # def itemChange(self, mouseEvent, change, value, ItemPositionChange):
    #     if change == ItemPositionChange: #and scene():
    #         newPos = QPointF()
    #         newPos = value.toPointF()
    #         if mouseEvent.button() != Qt.LeftButton: # and scene():
    #
    #             #customScene = scene()
    #             xV = round(newPos.x() / self.gridSize) * self.gridSize
    #             yV = round(newPos.y() / self.gridSize) * self.gridSize
    #             return QPointF(xV, yV)
    #         else:
    #             return newPos
    #     else:
    #         return QGraphicsItem.itemChange(change, value)

    def get_normal_item_by_uuid(self, uuid):
        for item in self.items():
            if isinstance(item, DiagramNormalItem) and item.uuid == uuid:
                return item

        return None

    def to_json(self) -> dict:
        items = []

        for item in self.items():
            if isinstance(item, DiagramNormalItem):
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

        return obj_dict

    def from_json(self, items_dict, context_menu: QMenu):
        arrow_items = []
        for item in items_dict["items"]:
            diagram_item = None
            str_item_type = item["item_type"]
            enum_item_type = EnumItemType[str_item_type]

            if enum_item_type == EnumItemType.Text:
                diagram_item = DiagramTextItem.from_dict(item, context_menu)
            elif enum_item_type == EnumItemType.Normal:
                diagram_item = DiagramNormalItem.from_dict(item, context_menu)
            elif enum_item_type == EnumItemType.Arrow:
                diagram_item = DiagramArrowItem.from_dict(item, context_menu)
                arrow_items.append(diagram_item)
            else:
                print(f"diagram scene from json error item type {enum_item_type}")

            if diagram_item is not None:
                print(f"add diagram item {diagram_item.item_type.name};{diagram_item.uuid} to scene")
                self.addItem(diagram_item)

        # 单独把创建的arrow 对象, 绑定到normal item 对象
        for arrow in arrow_items:
            start_item = self.get_normal_item_by_uuid(arrow.start_item_uuid)
            arrow.add_start_item(start_item)

            end_item = self.get_normal_item_by_uuid(arrow.end_item_uuid)
            arrow.add_end_item(end_item)

    def get_start_skill_diagram_item(self):
        for item in self.items():
            if isinstance(item, DiagramNormalItem):
                step = item.step
                if step is not None and step.type == EnumStepType.Stub:
                    if StepStub(step).stub_name == EnumStubName.StartSkill:
                        return item

        return None

    def get_diagram_item_stepN(self, item):
        for key, value in self.diagram_item_map_stepN.items():
            if value == item:
                return key

        return None

    def gen_skill_steps(self, diagram_item, stepN):
        sorted_steps_stack = []
        this_step = stepN

        step = diagram_item.step
        this_step, step_words = step.gen_step(this_step)
        sorted_steps_stack.append(step_words)
        self.diagram_item_map_stepN[this_step] = diagram_item

        def get_next_item_steps(stepN, next_item):
            this_step = stepN
            temp_steps_stack = []
            next_stepN = self.get_diagram_item_stepN(next_item)

            # 替换为goto，如果是已经执行过的step
            if next_stepN:
                this_step, step_words = StepGoto(gotostep=next_stepN).gen_step(this_step)
                temp_steps_stack.append(step_words)
            else:
                this_step, steps_stack = self.gen_skill_steps(true_next_item, this_step)
                temp_steps_stack.extend(steps_stack)

            return this_step, temp_steps_stack

        if diagram_item.diagram_type == DiagramNormalItem.Conditional:
            true_next_item = diagram_item.get_next_diagram_item(True)
            if true_next_item:
                this_step, steps_stack = get_next_item_steps(this_step, true_next_item)
                sorted_steps_stack.extend(steps_stack)

            this_step, step_words = StepStub(sname=EnumStubName.Else).gen_step(this_step)
            sorted_steps_stack.append(step_words)

            false_next_item = diagram_item.get_next_diagram_item(False)
            if false_next_item:
                this_step, steps_stack = get_next_item_steps(this_step, false_next_item)
                sorted_steps_stack.extend(steps_stack)
        else:
            next_item = diagram_item.get_next_diagram_item()
            if next_item:
                this_step, steps_stack = get_next_item_steps(this_step, next_item)
                sorted_steps_stack.extend(steps_stack)

        # need end stub steps
        if step.type in EnumStepType.need_end_step_stub_type_keys():
            if step.type == EnumStepType.CheckCondition.type_key():
                this_step, step_words = StepStub(sname=EnumStubName.EndCondition).gen_step(this_step)
                sorted_steps_stack.append(step_words)
            elif step.type == EnumStepType.Repeat.type_key():
                this_step, step_words = StepStub(sname=EnumStubName.EndLoop).gen_step(this_step)
                sorted_steps_stack.append(step_words)
            elif step.type == EnumStepType.CallFunction.type_key():
                this_step, step_words = StepStub(sname=EnumStubName.EndFunction).gen_step(this_step)
                sorted_steps_stack.append(step_words)
            elif step.type == EnumStepType.Stub.type_key():
                if step.stub_name == EnumStubName.StartSkill:
                    this_step, step_words = StepStub(sname=EnumStubName.EndSkill).gen_step(this_step)
                    sorted_steps_stack.append(step_words)

        return this_step, sorted_steps_stack

    def gen_psk_skill_file(self):
        psk_words = "{"
        first_step = 0

        # header
        skname, os, version, author, skid, desp = self.parent.skfc_infobox.get_skill_info()
        this_step, step_words = StepHeader(first_step, skname, os, version, author, skid, desp).gen_step(first_step)
        psk_words = psk_words + step_words

        # body steps
        sorted_steps_stack = []
        start_diagram_item = self.get_start_skill_diagram_item()
        print(f"start diagram item {start_diagram_item}")
        if start_diagram_item:
            this_step, steps_stack = self.gen_skill_steps(start_diagram_item, this_step)
            sorted_steps_stack.extend(steps_stack)

            step_words = ''.join(sorted_steps_stack)
            psk_words = psk_words + step_words
        else:
            print("Error No Start Skill Step Diagram Item")

        # dummy
        psk_words = psk_words + "\"dummy\" : \"\"}"
        print(psk_words)

        return psk_words



