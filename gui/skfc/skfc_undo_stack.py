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


class ChangeFontCommand(QUndoCommand):
    def __init__(self, item, oldFont, newFont, cb_fn):
        super().__init__()
        print("init ChangeFontCommand")
        self.item = item
        self.oldFont = oldFont
        self.newFont = newFont
        self.cb_fn = cb_fn

    def undo(self):
        print("undo set font ", self.oldFont)
        if self.item:
            self.item.set_font(self.oldFont)
        self.cb_fn(self.oldFont)

    def redo(self):
        print("undo set font ", self.newFont)
        if self.item:
            self.item.set_font(self.newFont)
        self.cb_fn(self.newFont)
