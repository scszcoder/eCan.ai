from PySide6.QtCore import (Signal, Qt, QPointF)
from PySide6.QtGui import QFont, QColor, QTextCursor
from PySide6.QtWidgets import QGraphicsItem, QGraphicsTextItem, QMenu

from gui.skfc.skfc_base import EnumItemType, SkFCBase


class DiagramTextItem(QGraphicsTextItem):
    lostFocus = Signal(QGraphicsTextItem)

    selectedChange = Signal(QGraphicsItem)

    def __init__(self, plain_text: str, font: QFont, color: QColor, position: QPointF,
                 uuid=None, context_menu=None, parent=None):
        super(DiagramTextItem, self).__init__(parent)

        self.uuid = uuid if uuid is not None else SkFCBase.build_uuid()
        self.item_type = EnumItemType.Text
        self.context_menu = context_menu
        self.parent = parent

        self.setPlainText(plain_text)
        self.setFont(font)
        self.setDefaultTextColor(color)
        self.setPos(position)

        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setTextInteractionFlags(Qt.NoTextInteraction)

        print(f"build diagram text item {plain_text}")

    # def itemChange(self, change, value):
    #     if change == QGraphicsItem.ItemSelectedChange:
    #         self.selectedChange.emit(self)
    #     return value

    def mouseDoubleClickEvent(self, event):
        if self.textInteractionFlags() == Qt.NoTextInteraction:
            self.setTextInteractionFlags(Qt.TextEditorInteraction)
            self.setPositionCursor(event.pos())
        super().mouseDoubleClickEvent(event)

    def setPositionCursor(self, pos):
        cursor = QTextCursor(self.document())
        cursor.setPosition(self.document().documentLayout().hitTest(pos, Qt.ExactHit))
        self.setTextCursor(cursor)

    def focusOutEvent(self, event):
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        super().focusOutEvent(event)

    def mousePressEvent(self, event):
        if self.textInteractionFlags() == Qt.TextEditorInteraction:
            self.setPositionCursor(event.pos())

        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        if self.context_menu is not None:
            self.scene().clearSelection()
            self.setSelected(True)
            self.context_menu.exec_(event.screenPos())

    def set_font(self, font: QFont):
        self.setFont(font)

    def to_dict(self):
        obj_dict = {
            "uuid": self.uuid,
            "item_type": EnumItemType.enum_name(self.item_type),
            "plain_text": self.toPlainText(),
            "position": SkFCBase.position_encode(self.pos()),
            "font": SkFCBase.font_encode(self.font()),
            "color": SkFCBase.color_encode(self.defaultTextColor()),
        }

        return obj_dict

    @classmethod
    def from_dict(cls, obj_dict, context_menu: QMenu):
        uuid = obj_dict["uuid"]
        plain_text = obj_dict["plain_text"]
        position = SkFCBase.position_decode(obj_dict["position"])
        font = SkFCBase.font_decode(obj_dict["font"])
        color = QColor(SkFCBase.color_decode(obj_dict["color"]))

        diagram_item_text = DiagramTextItem(plain_text=plain_text, font=font, color=color, position=position,
                                            uuid=uuid, context_menu=context_menu)

        return diagram_item_text
