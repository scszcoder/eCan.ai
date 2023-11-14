from PySide6.QtCore import (QRectF, QSize, Qt, QPointF)
from PySide6.QtGui import (QAction, QFont, QIcon, QBrush, QIcon, QPixmap, QPainter, QPen)
from PySide6.QtWidgets import (QGraphicsView, QHBoxLayout, QMenu, QMessageBox, QVBoxLayout, QWidget,
                               QButtonGroup, QGridLayout, QLabel, QSizePolicy, QToolBox, QToolButton, QWidget, QGraphicsView)
from config.app_info import app_info
from gui.diagram.diagram_scene import DiagramScene
from gui.diagram.diagram_item import DiagramItem
from gui.diagram.diagram_item_text import DiagramTextItem
from gui.diagram.diagram_item_arrow import DiagramArrowItem
from gui.diagram.diagram_toolbars import DiagramToolBars


class PyQDiagram(QWidget):
    InsertTextButton = 10

    def __init__(self):
        super(PyQDiagram, self).__init__()

        self.home_path = app_info.app_home_path

        self.createActions()

        self.context_menu = self.createMenus()
        # self.createMenuBars()

        self.diagram_scene = DiagramScene(self.context_menu)
        self.diagram_scene.setSceneRect(QRectF(0, 0, 500, 500))
        self.diagram_scene.itemInserted.connect(self.itemInserted)
        self.diagram_scene.textInserted.connect(self.textInserted)
        self.diagram_scene.arrowInserted.connect(self.arrowInserted)
        self.diagram_scene.itemSelected.connect(self.itemSelected)

        self.drawing_view = QGraphicsView(self.diagram_scene)
        # self.view.setRubberBandSelectionMode(Qt.IntersectsItemBoundingRect)
        # self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

        self.diagram_toolbox = self.create_toolbox()
        self.diagram_toolbars = DiagramToolBars(self.diagram_scene, self.drawing_view)

        body_layout = QHBoxLayout()
        body_layout.addWidget(self.diagram_toolbox)
        body_layout.addWidget(self.drawing_view)

        mainLayout = QVBoxLayout()
        mainLayout.addLayout(self.diagram_toolbars)
        mainLayout.addLayout(body_layout)

        self.widget = QWidget()
        self.widget.setLayout(mainLayout)
        print("init PyQDiagram")

        #self.setCentralWidget(self.widget)
        # self.setWindowTitle("Diagramscene")

    def deleteItem(self):
        for item in self.diagram_scene.selectedItems():
            if isinstance(item, DiagramItem):
                item.remove_arrows_items()
            elif isinstance(item, DiagramArrowItem):
                item.remove_item_target_arrow()
            elif isinstance(item, DiagramTextItem):
                pass

            self.diagram_scene.remove_diagram_item(item)

    def bringToFront(self):
        if not self.diagram_scene.selectedItems():
            return

        selectedItem = self.diagram_scene.selectedItems()[0]
        overlapItems = selectedItem.collidingItems()

        zValue = 0
        for item in overlapItems:
            if (item.zValue() >= zValue and isinstance(item, DiagramItem)):
                zValue = item.zValue() + 0.1
        selectedItem.setZValue(zValue)

    def sendToBack(self):
        if not self.diagram_scene.selectedItems():
            return

        selectedItem = self.diagram_scene.selectedItems()[0]
        overlapItems = selectedItem.collidingItems()

        zValue = 0
        for item in overlapItems:
            if (item.zValue() <= zValue and isinstance(item, DiagramItem)):
                zValue = item.zValue() - 0.1
        selectedItem.setZValue(zValue)

    def itemInserted(self, item):
        print("inserted normal item:", item, ">>", item.diagram_type)
        self.diagram_toolbars.pointerTypeGroup.button(DiagramScene.MoveItem).setChecked(True)
        self.diagram_scene.setMode(self.diagram_toolbars.pointerTypeGroup.checkedId())
        #self.diagram_button_group.button(item.diagramType).setChecked(False)
        self.diagram_button_group.button(item.diagram_type).setChecked(False)

        self.test_code_json()

    def textInserted(self, item):
        print(f"inserted text: {self.diagram_toolbars.pointerTypeGroup.checkedId()}")
        self.diagram_button_group.button(self.InsertTextButton).setChecked(False)
        self.diagram_scene.setMode(self.diagram_toolbars.pointerTypeGroup.checkedId())

        self.test_code_json()

    def arrowInserted(self, item):
        print(f"inserted arrow {item}")

        self.test_code_json()

    def test_code_json(self):
        pass
        # json_str = self.encode_json()
        # self.decode_json(json_str)

    def encode_json(self):
        json_str = self.diagram_scene.to_json()
        print(f"encode_json: {json_str}")
        return json_str

    def decode_json(self, json_str):
        items = DiagramScene.from_json(json_str, self.context_menu)
        print(f"decode json: {items}")

        for item in items:
            if isinstance(item, DiagramItem):
                item.name_text_item.setPlainText("normal#1")
                item.setPos(QPointF(item.pos().x() + 20, item.pos().y() + 20))
            elif isinstance(item, DiagramTextItem):
                item.setPlainText("text#1")
                item.setPos(QPointF(item.pos().x() + 20, item.pos().y() + 20))
            elif isinstance(item, DiagramArrowItem):
                # points = []
                # for point in item.path_points:
                #     points.append(QPointF(point.x() + 20, point.y() + 20))
                # item.render_arrow(points)
                pass
            else:
                print(f"decode_json error type item {item}")

            self.diagram_scene.addItem(item)

    def handleFontChange(self):
        self.diagram_toolbars.handleFontChange()

    def itemSelected(self, item):
        font = item.font()
        color = item.defaultTextColor()
        self.diagram_toolbars.fontCombo.setCurrentFont(font)
        self.diagram_toolbars.fontSizeCombo.setEditText(str(font.pointSize()))
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
                statusTip="Delete item from diagram",
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

    def create_toolbox(self):
        self.diagram_button_group = QButtonGroup()
        self.diagram_button_group.setExclusive(False)
        # self.diagram_button_group.buttonClicked[int].connect(self.diagram_button_group_clicked)
        self.diagram_button_group.buttonClicked.connect(self.diagram_button_group_clicked)

        layout = QGridLayout()
        layout.addWidget(self.createCellWidget("Conditional", DiagramItem.Conditional), 0, 0)
        layout.addWidget(self.createCellWidget("Process", DiagramItem.Step), 0, 1)
        layout.addWidget(self.createCellWidget("Input/Output", DiagramItem.Io), 1, 0)
        layout.addWidget(self.createCellWidget("Start/End", DiagramItem.StartEnd), 1, 1)
        layout.addWidget(self.create_text_cell_widget(), 2, 0)

        layout.setRowStretch(3, 10)
        layout.setColumnStretch(2, 10)

        diagram_item_widget = QWidget()
        diagram_item_widget.setLayout(layout)

        self.background_button_group = QButtonGroup()
        self.background_button_group.buttonClicked.connect(self.background_button_group_clicked)

        backgroundLayout = QGridLayout()
        backgroundLayout.addWidget(
            self.createBackgroundCellWidget("Blue Grid",
                                            self.home_path + '/resource/images/skill_editor/background1.png'), 0, 0)
        backgroundLayout.addWidget(
            self.createBackgroundCellWidget("White Grid",
                                            self.home_path + '/resource/images/skill_editor/background2.png'), 0, 1)
        backgroundLayout.addWidget(
            self.createBackgroundCellWidget("Gray Grid",
                                            self.home_path + '/resource/images/skill_editor/background3.png'), 1, 0)
        backgroundLayout.addWidget(
            self.createBackgroundCellWidget("No Grid",
                                            self.home_path + '/resource/images/skill_editor/background4.png'), 1, 1)

        backgroundLayout.setRowStretch(2, 10)
        backgroundLayout.setColumnStretch(2, 10)

        background_widget = QWidget()
        background_widget.setLayout(backgroundLayout)

        toolbox = QToolBox()
        toolbox.setSizePolicy(QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Ignored))
        toolbox.setMinimumWidth(diagram_item_widget.sizeHint().width())
        toolbox.addItem(diagram_item_widget, "Basic Flowchart Shapes")
        toolbox.addItem(background_widget, "Backgrounds")

        return toolbox

    def diagram_button_group_clicked(self, button):
        print("diagram button group clicked:", self.diagram_button_group.id(button))
        buttons = self.diagram_button_group.buttons()
        for mbutton in buttons:
            #if self.diagram_button_group.button(id) != mbutton:
            if button != mbutton:
                button.setChecked(False)

        #if id == self.InsertTextButton:
        if self.diagram_button_group.id(button) == self.InsertTextButton:
            self.diagram_scene.setMode(DiagramScene.InsertText)
        else:
            #self.scene.setItemType(id)
            self.diagram_scene.setItemType(self.diagram_button_group.id(button))
            self.diagram_scene.setMode(DiagramScene.InsertItem)

    def background_button_group_clicked(self, button):
        buttons = self.background_button_group.buttons()
        for myButton in buttons:
            if myButton != button:
                button.setChecked(False)

        text = button.text()
        if text == "Blue Grid":
            self.diagram_scene.setBackgroundBrush(QBrush(QPixmap(self.home_path + '/resource/images/skill_editor/background1.png')))
        elif text == "White Grid":
            self.diagram_scene.setBackgroundBrush(QBrush(QPixmap(self.home_path + '/resource/images/skill_editor/background2.png')))
        elif text == "Gray Grid":
            self.diagram_scene.setBackgroundBrush(QBrush(QPixmap(self.home_path + '/resource/images/skill_editor/background3.png')))
        else:
            self.diagram_scene.setBackgroundBrush(QBrush(QPixmap(self.home_path + '/resource/images/skill_editor/background4.png')))

        #self.scene.update()
        #self.view.update()

    def create_text_cell_widget(self):
        textButton = QToolButton()
        textButton.setCheckable(True)
        self.diagram_button_group.addButton(textButton, self.InsertTextButton)
        textButton.setIcon(
            QIcon(QPixmap(self.home_path + '/resource/images/skill_editor/textpointer.png').scaled(30, 30)))
        textButton.setIconSize(QSize(32, 32))

        textLayout = QGridLayout()
        textLayout.addWidget(textButton, 0, 0, Qt.AlignHCenter)
        textLayout.addWidget(QLabel("Text"), 1, 0, Qt.AlignCenter)

        textWidget = QWidget()
        textWidget.setLayout(textLayout)

        return textWidget

    def createBackgroundCellWidget(self, text, image):
        button = QToolButton()
        button.setText(text)
        button.setIcon(QIcon(image))
        button.setIconSize(QSize(50, 50))
        button.setCheckable(True)
        self.background_button_group.addButton(button)

        layout = QGridLayout()
        layout.addWidget(button, 0, 0, Qt.AlignHCenter)
        layout.addWidget(QLabel(text), 1, 0, Qt.AlignCenter)

        widget = QWidget()
        widget.setLayout(layout)

        return widget

    def createCellWidget(self, text, diagram_type):
        # item = DiagramItem(diagramType, )
        print("creating widget type:", diagram_type)
        icon = QIcon(self.diagram_icon_image(diagram_type))

        button = QToolButton()
        button.setIcon(icon)
        button.setIconSize(QSize(32, 32))
        button.setCheckable(True)
        self.diagram_button_group.addButton(button, diagram_type)

        layout = QGridLayout()
        layout.addWidget(button, 0, 0, Qt.AlignHCenter)
        layout.addWidget(QLabel(text), 1, 0, Qt.AlignCenter)

        widget = QWidget()
        widget.setLayout(layout)

        return widget

    def diagram_icon_image(self, diagram_type):
        pixmap = QPixmap(250, 250)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setPen(QPen(Qt.black, 8))
        painter.translate(125, 125)
        painter.drawPolyline(DiagramItem.create_item_polygon(diagram_type))

        return pixmap

