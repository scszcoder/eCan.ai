from PySide6.QtGui import QUndoCommand


class AddDiagramItemCommand(QUndoCommand):
    def __init__(self, scene, item):
        super().__init__()
        self.scene = scene
        self.item = item

    def undo(self):
        print("undo item ", self.item)
        self.scene.removeItem(self.item)

    def redo(self):
        print("redo item ", self.item)
        self.scene.addItem(self.item)


class RemoveDiagramItemCommand(QUndoCommand):
    def __init__(self, scene, item):
        super().__init__()
        self.scene = scene
        self.item = item

    def undo(self):
        self.scene.addItem(self.item)

    def redo(self):
        self.scene.removeItem(self.item)


class ChangeColorCommand(QUndoCommand):
    def __init__(self, item, oldColor, newColor):
        super().__init__()
        self.item = item
        self.oldColor = oldColor
        self.newColor = newColor

    def undo(self):
        print("undo set old color ", self.oldColor)
        self.item.setBrush(self.oldColor)

    def redo(self):
        print("redo set new color ", self.newColor)
        self.item.setBrush(self.newColor)