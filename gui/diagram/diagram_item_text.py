from PySide6.QtCore import (Signal, Qt, QPointF)
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import QGraphicsItem, QGraphicsTextItem, QMenu

from gui.diagram.diagram_base import EnumItemType, DiagramBase


class DiagramTextItem(QGraphicsTextItem):
    lostFocus = Signal(QGraphicsTextItem)

    selectedChange = Signal(QGraphicsItem)

    def __init__(self, plain_text: str, font: QFont, color: QColor, position: QPointF,
                 uuid=None, sub_item=True, context_menu=None, parent=None):
        super(DiagramTextItem, self).__init__(parent)

        self.uuid = uuid if uuid is not None else DiagramBase.build_uuid()
        self.item_type = EnumItemType.Text
        self.sub_item = sub_item
        self.context_menu = context_menu

        self.setPlainText(plain_text)
        self.setFont(font)
        self.setDefaultTextColor(color)
        self.setPos(position)

        if self.sub_item is False:
            self.setFlag(QGraphicsItem.ItemIsMovable)

        self.setFlag(QGraphicsItem.ItemIsSelectable)

        print(f"build diagram text item {plain_text}, sub item: {self.sub_item}")

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

    def contextMenuEvent(self, event):
        if self.sub_item is False and self.context_menu is not None:
            self.scene().clearSelection()
            self.setSelected(True)
            self.context_menu.exec_(event.screenPos())

    def set_font(self, font: QFont):
        self.setFont(font)

    def to_dict(self):
        obj_dict = {
            "uuid": self.uuid,
            "item_type": EnumItemType.enum_name(self.item_type),
            "sub_item": self.sub_item,
            "plain_text": self.toPlainText(),
            "position": DiagramBase.position_encode(self.pos()),
            "font": DiagramBase.font_encode(self.font()),
            "color": DiagramBase.color_encode(self.defaultTextColor()),
        }

        return obj_dict

    @classmethod
    def from_dict(cls, obj_dict, context_menu: QMenu):
        uuid = obj_dict["uuid"]
        sub_item = obj_dict["sub_item"]
        plain_text = obj_dict["plain_text"]
        position = DiagramBase.position_decode(obj_dict["position"])
        font = DiagramBase.font_decode(obj_dict["font"])
        color = QColor(DiagramBase.color_decode(obj_dict["color"]))

        diagram_item_text = DiagramTextItem(plain_text=plain_text, font=font, color=color, position=position,
                                            uuid=uuid, sub_item=sub_item, context_menu=context_menu)

        return diagram_item_text
