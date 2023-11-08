from PySide6.QtCore import (Signal, Qt)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsTextItem


class DiagramTextItem(QGraphicsTextItem):
    lostFocus = Signal(QGraphicsTextItem)

    selectedChange = Signal(QGraphicsItem)

    def __init__(self, parent=None, scene=None, subItem=True, contextMenu=None):
        super(DiagramTextItem, self).__init__(parent, scene)

        self.isSubItem = subItem
        self.myContextMenu = contextMenu

        if self.isSubItem is False:
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

    def contextMenuEvent(self, event):
        if self.isSubItem is False and self.myContextMenu is not None:
            self.scene().clearSelection()
            self.setSelected(True)
            self.myContextMenu.exec_(event.screenPos())
