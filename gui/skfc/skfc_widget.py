import json

from PySide6.QtCore import (QRectF, QSize, Qt)
from PySide6.QtGui import (QAction, QFont,  QIcon)
from PySide6.QtWidgets import (QHBoxLayout, QMenu, QMessageBox, QVBoxLayout, QWidget, QGraphicsView,
                               QSplitter)
from config.app_info import app_info
from gui.skfc.skfc_scene import SkFCScene
from gui.skfc.diagram_item_normal import DiagramNormalItem
from gui.skfc.skfc_toolbars import SkFCToolBars
from skfc.skfc_infobox import SkFCInfoBox
from skfc.skfc_toolbox import SkFCToolBox


class SkFCView(QGraphicsView):
    def __init__(self, scene: SkFCScene):
        super(SkFCView, self).__init__(scene)
        self.skfc_scene = scene
        # self.view.setRubberBandSelectionMode(Qt.IntersectsItemBoundingRect)
        # self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        # self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 调整场景的矩形区域以匹配视图的大小
        # self.scene().setSceneRect(self.rect())

    def showEvent(self, event):
        super().showEvent(event)
        # self.setCursor(Qt.ArrowCursor)

    # def mousePressEvent(self, event):
    #     item = self.itemAt(event.pos())  # 获取点击位置的元素
    #     scene = self.scene()
    #     if not item or (scene.focusItem() and item != scene.focusItem()):
    #         scene.clearFocus()  # 清除焦点
    #     super().mousePressEvent(event)

    # def mouseDoubleClickEvent(self, event):
    #     pos = event.pos()
    #     items = self.items(pos.x(), pos.y())
    #
    #     for item in items:
    #         if isinstance(item, QGraphicsPathItem) and item.hasFocus():
    #             item.mouseDoubleClickEvent(event)
    #             return
    #
    #     super().mouseDoubleClickEvent(event)
    #
    # def mousePressEvent(self, event):
    #     # 当点击其他元素时，设置焦点到该元素
    #     item = self.itemAt(event.pos())
    #     if item and item != self.scene().focusItem():
    #         item.setFocus()
    #     super().mousePressEvent(event)


class SkFCWidget(QWidget):
    # InsertTextButton = 10

    def __init__(self):
        super(SkFCWidget, self).__init__()

        self.home_path = app_info.app_home_path

        self.createActions()
        self.context_menu = self.createMenus()
        # self.createMenuBars()

        self.skfc_scene = SkFCScene(self.context_menu, self)
        self.skfc_scene.setSceneRect(QRectF(0, 0, 600, 1000))
        self.skfc_scene.itemInserted.connect(self.itemInserted)
        self.skfc_scene.textInserted.connect(self.textInserted)
        self.skfc_scene.arrowInserted.connect(self.arrowInserted)
        self.skfc_scene.itemSelected.connect(self.itemSelected)

        self.skfc_view = SkFCView(self.skfc_scene)
        self.skfc_toolbox = SkFCToolBox(self.skfc_scene, self.skfc_view)
        self.skfc_toolbars = SkFCToolBars(self.skfc_scene, self.skfc_view)
        self.skfc_infobox = SkFCInfoBox(self.skfc_scene, self.skfc_view)

        self.vsplitter_body = QSplitter(Qt.Horizontal)
        self.vsplitter_body.addWidget(self.skfc_toolbox)
        self.vsplitter_body.addWidget(self.skfc_view)
        self.vsplitter_body.addWidget(self.skfc_infobox)

        body_layout = QHBoxLayout()
        body_layout.addWidget(self.vsplitter_body)

        mainLayout = QVBoxLayout()
        mainLayout.addLayout(self.skfc_toolbars)
        mainLayout.addLayout(body_layout)

        self.setLayout(mainLayout)
        print("init SkFc widget")

    def deleteItem(self):
        for item in self.skfc_scene.selectedItems():
            self.skfc_scene.remove_diagram_item(item)

    def bringToFront(self):
        if not self.skfc_scene.selectedItems():
            return

        selectedItem = self.skfc_scene.selectedItems()[0]
        overlapItems = selectedItem.collidingItems()

        zValue = 0
        for item in overlapItems:
            if (item.zValue() >= zValue and isinstance(item, DiagramNormalItem)):
                zValue = item.zValue() + 0.1
        selectedItem.setZValue(zValue)

    def sendToBack(self):
        if not self.skfc_scene.selectedItems():
            return

        selectedItem = self.skfc_scene.selectedItems()[0]
        overlapItems = selectedItem.collidingItems()

        zValue = 0
        for item in overlapItems:
            if (item.zValue() <= zValue and isinstance(item, DiagramNormalItem)):
                zValue = item.zValue() - 0.1
        selectedItem.setZValue(zValue)

    def itemInserted(self, item):
        print("inserted normal item:", item, ">>", item.diagram_type)
        self.skfc_toolbars.pointerTypeGroup.button(SkFCScene.MoveItem).setChecked(True)
        self.skfc_scene.setMode(self.skfc_toolbars.pointerTypeGroup.checkedId())
        #self.diagram_button_group.button(item.diagramType).setChecked(False)
        self.skfc_toolbox.diagram_button_group.button(item.diagram_type).setChecked(False)

    def textInserted(self, item):
        print(f"inserted text: {self.skfc_toolbars.pointerTypeGroup.checkedId()}")
        self.skfc_toolbox.diagram_button_group.button(SkFCToolBox.InsertTextButton).setChecked(False)
        self.skfc_toolbars.pointerTypeGroup.button(SkFCScene.MoveItem).setChecked(True)
        self.skfc_scene.setMode(self.skfc_toolbars.pointerTypeGroup.checkedId())

    def arrowInserted(self, item):
        print(f"inserted arrow {item}")
        pass

    def encode_json(self, indent=None) -> str:
        json_dict = self.skfc_scene.to_json()
        json_str = json.dumps(json_dict, indent=indent)
        print(f"encode json str: {json_str}")

        return json_str

    def decode_json(self, json_str):
        items_dict = json.loads(json_str)
        self.skfc_scene.from_json(items_dict, self.context_menu)

    def handleFontChange(self):
        self.skfc_toolbars.handleFontChange()

    def itemSelected(self, item):
        font = item.font()
        color = item.defaultTextColor()
        self.skfc_toolbars.fontCombo.setCurrentFont(font)
        self.skfc_toolbars.fontSizeCombo.setEditText(str(font.pointSize()))
        self.boldAction.setChecked(font.weight() == QFont.Bold)
        self.italicAction.setChecked(font.italic())
        self.underlineAction.setChecked(font.underline())

    def about(self):
        QMessageBox.about(self, "About Diagram Scene", "The <b>Diagram Scene</b> example shows use of the graphics framework.")

    def createActions(self):
        self.toFrontAction = QAction(
                QIcon(self.home_path + '/resource/images/skill_editor/bringtofront.png'), "Bring to &Front",
                self, shortcut="Ctrl+F", statusTip="Bring item to front",
                triggered=self.bringToFront)

        self.sendBackAction = QAction(
                QIcon(self.home_path + '/resource/images/skill_editor/sendtoback.png'), "Send to &Back", self,
                shortcut="Ctrl+B", statusTip="Send item to back",
                triggered=self.sendToBack)

        self.deleteAction = QAction(QIcon(self.home_path + '/resource/images/skill_editor/delete.png'),
                "&Delete", self, shortcut="Delete",
                statusTip="Delete item from skfc",
                triggered=self.deleteItem)

        self.exitAction = QAction("E&xit", self, shortcut="Ctrl+X",
                statusTip="Quit Scenediagram example", triggered=self.close)

        self.boldAction = QAction(QIcon(self.home_path + '/resource/images/skill_editor/bold.png'),
                "Bold", self, checkable=True, shortcut="Ctrl+B",
                triggered=self.handleFontChange)

        self.italicAction = QAction(QIcon(self.home_path + '/resource/images/skill_editor/italic.png'),
                "Italic", self, checkable=True, shortcut="Ctrl+I",
                triggered=self.handleFontChange)

        self.underlineAction = QAction(
                QIcon(self.home_path + '/resource/images/skill_editor/underline.png'), "Underline", self,
                checkable=True, shortcut="Ctrl+U",
                triggered=self.handleFontChange)

        self.aboutAction = QAction("A&bout", self, shortcut="Ctrl+B",
                triggered=self.about)

    def createMenus(self):
        item_menu = QMenu("&Item")
        item_menu.addAction(self.deleteAction)
        item_menu.addSeparator()
        item_menu.addAction(self.toFrontAction)
        item_menu.addAction(self.sendBackAction)

        return item_menu

    # def createMenuBars(self):
    #     self.fileMenu = self.menuBar().addMenu("&File")
    #     self.fileMenu.addAction(self.exitAction)
    #
    #     self.menuBar().addMenu(self.itemMenu)
    #
    #     self.aboutMenu = self.menuBar().addMenu("&Help")
    #     self.aboutMenu.addAction(self.aboutAction)


