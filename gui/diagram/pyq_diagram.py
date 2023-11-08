from PySide6.QtCore import (QRect, QRectF, QSize, Qt)
from PySide6.QtGui import (QAction, QBrush, QColor, QFont, QIcon, QIntValidator, QPainter, QPixmap)
from PySide6 import QtCore, QtWidgets
from PySide6.QtWidgets import QButtonGroup, QComboBox, QFontComboBox, QGraphicsView, QGridLayout, \
                            QHBoxLayout, QLabel, QMenu, QMessageBox, QSizePolicy, \
                            QVBoxLayout, QToolBox, QToolButton, QWidget
from config.app_info import app_info
from gui.diagram.diagram_scene import DiagramScene
from gui.diagram.diagram_item import DiagramItem
from gui.diagram.diagram_item_arrow import DiagramArrowItem


class PyQDiagram(QWidget):
    InsertTextButton = 10

    def __init__(self):
        super(PyQDiagram, self).__init__()

        self.home_path = app_info.app_home_path
        self.createActions()
        self.createMenus()
        # self.createMenuBars()
        self.createToolBox()

        self.scene = DiagramScene(self.itemMenu)
        #self.scene.setSceneRect(QRectF(0, 0, 5000, 5000))
        self.scene.setSceneRect(QRectF(0, 0, 500, 500))
        self.scene.itemInserted.connect(self.itemInserted)
        self.scene.textInserted.connect(self.textInserted)
        self.scene.itemSelected.connect(self.itemSelected)

        #self.createToolbars()
        self.createPseudoToolbars()
        self.test_label = QtWidgets.QLabel("Houston Houston", alignment=QtCore.Qt.AlignLeft)
        layout = QHBoxLayout()
        mainLayout = QVBoxLayout()
        #layout.addWidget(self.test_label)
        layout.addWidget(self.toolBox)
        self.view = QGraphicsView(self.scene)
        # self.view.setRubberBandSelectionMode(Qt.IntersectsItemBoundingRect)
        # self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        layout.addWidget(self.view)
        mainLayout.addLayout(self.ToolBarLayout)
        mainLayout.addLayout(layout)

        self.widget = QWidget()
        self.widget.setLayout(mainLayout)
        print("what????")

        #self.setCentralWidget(self.widget)
        # self.setWindowTitle("Diagramscene")

    def backgroundButtonGroupClicked(self, button):
        buttons = self.backgroundButtonGroup.buttons()
        for myButton in buttons:
            if myButton != button:
                button.setChecked(False)

        text = button.text()
        if text == "Blue Grid":
            self.scene.setBackgroundBrush(QBrush(QPixmap(self.home_path + '/resource/images/skill_editor/background1.png')))
        elif text == "White Grid":
            self.scene.setBackgroundBrush(QBrush(QPixmap(self.home_path + '/resource/images/skill_editor/background2.png')))
        elif text == "Gray Grid":
            self.scene.setBackgroundBrush(QBrush(QPixmap(self.home_path + '/resource/images/skill_editor/background3.png')))
        else:
            self.scene.setBackgroundBrush(QBrush(QPixmap(self.home_path + '/resource/images/skill_editor/background4.png')))

        #self.scene.update()
        #self.view.update()

    #def buttonGroupClicked(self, id):
    def buttonGroupClicked(self, button):
        print("clicked:", button)
        buttons = self.buttonGroup.buttons()
        for mbutton in buttons:
            #if self.buttonGroup.button(id) != mbutton:
            if button != mbutton:
                button.setChecked(False)

        #if id == self.InsertTextButton:
        if self.buttonGroup.id(button) == self.InsertTextButton:
            self.scene.setMode(DiagramScene.InsertText)
        else:
            #self.scene.setItemType(id)
            self.scene.setItemType(self.buttonGroup.id(button))
            self.scene.setMode(DiagramScene.InsertItem)

    def deleteItem(self):
        for item in self.scene.selectedItems():
            if isinstance(item, DiagramItem):
                item.remove_arrows_items()
            elif isinstance(item, DiagramArrowItem):
                item.remove_item_target_arrow()

            self.scene.removeItem(item)

    def pointerGroupClicked(self, i):
        self.scene.setMode(self.pointerTypeGroup.checkedId())

    def txtPropertyGroupClicked(self, i):
        self.handleFontChange()

    def bringToFront(self):
        if not self.scene.selectedItems():
            return

        selectedItem = self.scene.selectedItems()[0]
        overlapItems = selectedItem.collidingItems()

        zValue = 0
        for item in overlapItems:
            if (item.zValue() >= zValue and isinstance(item, DiagramItem)):
                zValue = item.zValue() + 0.1
        selectedItem.setZValue(zValue)

    def sendToBack(self):
        if not self.scene.selectedItems():
            return

        selectedItem = self.scene.selectedItems()[0]
        overlapItems = selectedItem.collidingItems()

        zValue = 0
        for item in overlapItems:
            if (item.zValue() <= zValue and isinstance(item, DiagramItem)):
                zValue = item.zValue() - 0.1
        selectedItem.setZValue(zValue)

    def itemInserted(self, item):
        print("inserted item:", item, ">>", item.diagramType)
        self.pointerTypeGroup.button(DiagramScene.MoveItem).setChecked(True)
        self.scene.setMode(self.pointerTypeGroup.checkedId())
        #self.buttonGroup.button(item.diagramType).setChecked(False)
        self.buttonGroup.button(item.diagramType).setChecked(False)

    def textInserted(self, item):
        print(f"inserted text: {self.pointerTypeGroup.checkedId()}")
        self.buttonGroup.button(self.InsertTextButton).setChecked(False)
        self.scene.setMode(self.pointerTypeGroup.checkedId())

    def currentFontChanged(self, font):
        self.handleFontChange()

    def fontSizeChanged(self, font):
        self.handleFontChange()

    def sceneScaleChanged(self, scale):
        scaleString = self.sceneScaleCombo.currentText()
        print("scale changed to: ", scaleString)
        newScale = float(scaleString[:scaleString.index("%")]) / 100.0
        print("scale number:" + str(newScale))
        # newScale = scale.left(scale.indexOf("%")).toDouble()[0] / 100.0
        #oldMatrix = self.view.matrix()
        oldMatrix = self.view.transform()
        # self.view.resetMatrix()
        self.view.resetTransform()
        self.view.translate(oldMatrix.dx(), oldMatrix.dy())
        self.view.scale(newScale, newScale)

    def textColorChanged(self):
        self.textAction = self.sender()
        self.fontColorToolButton.setIcon(
                self.createColorToolButtonIcon(self.home_path + '/resource/images/skill_editor/textpointer.png',
                        QColor(self.textAction.data())))
        self.textButtonTriggered()

    def itemColorChanged(self):
        self.fillAction = self.sender()
        self.fillColorToolButton.setIcon(
                self.createColorToolButtonIcon( self.home_path + '/resource/images/skill_editor/floodfill.png',
                        QColor(self.fillAction.data())))
        self.fillButtonTriggered()

    def lineColorChanged(self):
        self.lineAction = self.sender()
        self.lineColorToolButton.setIcon(
                self.createColorToolButtonIcon(self.home_path + '/resource/images/skill_editor/linecolor.png',
                        QColor(self.lineAction.data())))
        self.lineButtonTriggered()

    def textButtonTriggered(self):
        self.scene.setTextColor(QColor(self.textAction.data()))

    def fillButtonTriggered(self):
        self.scene.setItemColor(QColor(self.fillAction.data()))

    def lineButtonTriggered(self):
        self.scene.setLineColor(QColor(self.lineAction.data()))

    def handleFontChange(self):
        font = self.fontCombo.currentFont()
        font.setPointSize(int(self.fontSizeCombo.currentText()))
        #if self.boldAction.isChecked():
        if self.txtBoldButton.isChecked():
            font.setWeight(QFont.Bold)
        else:
            font.setWeight(QFont.Normal)
        #font.setItalic(self.italicAction.isChecked())
        #font.setUnderline(self.underlineAction.isChecked())
        font.setItalic(self.txtItalicButton.isChecked())
        font.setUnderline(self.txtUnderlineButton.isChecked())

        self.scene.setFont(font)

    def itemSelected(self, item):
        font = item.font()
        color = item.defaultTextColor()
        self.fontCombo.setCurrentFont(font)
        self.fontSizeCombo.setEditText(str(font.pointSize()))
        self.boldAction.setChecked(font.weight() == QFont.Bold)
        self.italicAction.setChecked(font.italic())
        self.underlineAction.setChecked(font.underline())

    def about(self):
        QMessageBox.about(self, "About Diagram Scene", "The <b>Diagram Scene</b> example shows use of the graphics framework.")

    def createToolBox(self):
        self.buttonGroup = QButtonGroup()
        self.buttonGroup.setExclusive(False)
        #self.buttonGroup.buttonClicked[int].connect(self.buttonGroupClicked)
        self.buttonGroup.buttonClicked.connect(self.buttonGroupClicked)

        layout = QGridLayout()
        layout.addWidget(self.createCellWidget("Conditional", DiagramItem.Conditional), 0, 0)
        layout.addWidget(self.createCellWidget("Process", DiagramItem.Step), 0, 1)
        layout.addWidget(self.createCellWidget("Input/Output", DiagramItem.Io), 1, 0)
        layout.addWidget(self.createCellWidget("Start/End", DiagramItem.StartEnd), 1, 1)

        textButton = QToolButton()
        textButton.setCheckable(True)
        self.buttonGroup.addButton(textButton, self.InsertTextButton)
        textButton.setIcon(QIcon(QPixmap(self.home_path + '/resource/images/skill_editor/textpointer.png').scaled(30, 30)))
        textButton.setIconSize(QSize(32, 32))

        textLayout = QGridLayout()
        textLayout.addWidget(textButton, 0, 0, Qt.AlignHCenter)
        textLayout.addWidget(QLabel("Text"), 1, 0, Qt.AlignCenter)
        textWidget = QWidget()
        textWidget.setLayout(textLayout)
        layout.addWidget(textWidget, 2, 0)

        layout.setRowStretch(3, 10)
        layout.setColumnStretch(2, 10)

        itemWidget = QWidget()
        itemWidget.setLayout(layout)

        self.backgroundButtonGroup = QButtonGroup()
        self.backgroundButtonGroup.buttonClicked.connect(self.backgroundButtonGroupClicked)

        backgroundLayout = QGridLayout()
        backgroundLayout.addWidget(
                self.createBackgroundCellWidget("Blue Grid", self.home_path + '/resource/images/skill_editor/background1.png'), 0, 0)
        backgroundLayout.addWidget(
                self.createBackgroundCellWidget("White Grid", self.home_path + '/resource/images/skill_editor/background2.png'), 0, 1)
        backgroundLayout.addWidget(
                self.createBackgroundCellWidget("Gray Grid", self.home_path + '/resource/images/skill_editor/background3.png'), 1, 0)
        backgroundLayout.addWidget(
                self.createBackgroundCellWidget("No Grid", self.home_path + '/resource/images/skill_editor/background4.png'), 1, 1)

        backgroundLayout.setRowStretch(2, 10)
        backgroundLayout.setColumnStretch(2, 10)

        backgroundWidget = QWidget()
        backgroundWidget.setLayout(backgroundLayout)

        self.toolBox = QToolBox()
        self.toolBox.setSizePolicy(QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Ignored))
        self.toolBox.setMinimumWidth(itemWidget.sizeHint().width())
        self.toolBox.addItem(itemWidget, "Basic Flowchart Shapes")
        self.toolBox.addItem(backgroundWidget, "Backgrounds")

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
        self.itemMenu = QMenu("&Item")
        self.itemMenu.addAction(self.deleteAction)
        self.itemMenu.addSeparator()
        self.itemMenu.addAction(self.toFrontAction)
        self.itemMenu.addAction(self.sendBackAction)

    def createMenuBars(self):
        self.fileMenu = self.menuBar().addMenu("&File")
        self.fileMenu.addAction(self.exitAction)

        self.menuBar().addMenu(self.itemMenu)

        self.aboutMenu = self.menuBar().addMenu("&Help")
        self.aboutMenu.addAction(self.aboutAction)

    # def createToolbars(self):
    #     self.editToolBar = self.addToolBar("Edit")
    #     self.editToolBar.addAction(self.deleteAction)
    #     self.editToolBar.addAction(self.toFrontAction)
    #     self.editToolBar.addAction(self.sendBackAction)
    #
    #     self.fontCombo = QFontComboBox()
    #     self.fontCombo.currentFontChanged.connect(self.currentFontChanged)
    #
    #     self.fontSizeCombo = QComboBox()
    #     self.fontSizeCombo.setEditable(True)
    #     for i in range(8, 30, 2):
    #         self.fontSizeCombo.addItem(str(i))
    #     validator = QIntValidator(2, 64, self)
    #     self.fontSizeCombo.setValidator(validator)
    #     self.fontSizeCombo.currentIndexChanged.connect(self.fontSizeChanged)
    #
    #     self.fontColorToolButton = QToolButton()
    #     self.fontColorToolButton.setPopupMode(QToolButton.MenuButtonPopup)
    #     self.fontColorToolButton.setMenu(
    #             self.createColorMenu(self.textColorChanged, Qt.black))
    #     self.textAction = self.fontColorToolButton.menu().defaultAction()
    #     self.fontColorToolButton.setIcon(
    #             self.createColorToolButtonIcon(self.home_path + '/resource/images/skill_editor/textpointer.png',
    #                     Qt.black))
    #     self.fontColorToolButton.setAutoFillBackground(True)
    #     self.fontColorToolButton.clicked.connect(self.textButtonTriggered)
    #
    #     self.fillColorToolButton = QToolButton()
    #     self.fillColorToolButton.setPopupMode(QToolButton.MenuButtonPopup)
    #     self.fillColorToolButton.setMenu(
    #             self.createColorMenu(self.itemColorChanged, Qt.white))
    #     self.fillAction = self.fillColorToolButton.menu().defaultAction()
    #     self.fillColorToolButton.setIcon(
    #             self.createColorToolButtonIcon(self.home_path + '/resource/images/skill_editor/floodfill.png',
    #                     Qt.white))
    #     self.fillColorToolButton.clicked.connect(self.fillButtonTriggered)
    #
    #     self.lineColorToolButton = QToolButton()
    #     self.lineColorToolButton.setPopupMode(QToolButton.MenuButtonPopup)
    #     self.lineColorToolButton.setMenu(
    #             self.createColorMenu(self.lineColorChanged, Qt.black))
    #     self.lineAction = self.lineColorToolButton.menu().defaultAction()
    #     self.lineColorToolButton.setIcon(
    #             self.createColorToolButtonIcon(self.home_path + '/resource/images/skill_editor/linecolor.png',
    #                     Qt.black))
    #     self.lineColorToolButton.clicked.connect(self.lineButtonTriggered)
    #
    #     self.textToolBar = self.addToolBar("Font")
    #     self.textToolBar.addWidget(self.fontCombo)
    #     self.textToolBar.addWidget(self.fontSizeCombo)
    #     self.textToolBar.addAction(self.boldAction)
    #     self.textToolBar.addAction(self.italicAction)
    #     self.textToolBar.addAction(self.underlineAction)
    #
    #     self.colorToolBar = self.addToolBar("Color")
    #     self.colorToolBar.addWidget(self.fontColorToolButton)
    #     self.colorToolBar.addWidget(self.fillColorToolButton)
    #     self.colorToolBar.addWidget(self.lineColorToolButton)
    #
    #     pointerButton = QToolButton()
    #     pointerButton.setCheckable(True)
    #     pointerButton.setChecked(True)
    #     pointerButton.setIcon(QIcon(self.home_path + '/resource/images/skill_editor/pointer.png'))
    #     linePointerButton = QToolButton()
    #     linePointerButton.setCheckable(True)
    #     linePointerButton.setIcon(QIcon(self.home_path + '/resource/images/skill_editor/linepointer.png'))
    #
    #     self.pointerTypeGroup = QButtonGroup()
    #     self.pointerTypeGroup.addButton(pointerButton, DiagramScene.MoveItem)
    #     self.pointerTypeGroup.addButton(linePointerButton, DiagramScene.InsertLine)
    #     # self.pointerTypeGroup.buttonClicked[int].connect(self.pointerGroupClicked)
    #     self.pointerTypeGroup.buttonClicked.connect(self.pointerGroupClicked)
    #
    #
    #     self.sceneScaleCombo = QComboBox()
    #     self.sceneScaleCombo.addItems(["50%", "75%", "100%", "125%", "150%"])
    #     self.sceneScaleCombo.setCurrentIndex(2)
    #     self.sceneScaleCombo.currentIndexChanged[str].connect(self.sceneScaleChanged)
    #
    #     self.pointerToolbar = self.addToolBar("Pointer type")
    #     self.pointerToolbar.addWidget(pointerButton)
    #     self.pointerToolbar.addWidget(linePointerButton)
    #     self.pointerToolbar.addWidget(self.sceneScaleCombo)

    def createPseudoToolbars(self):
        self.ToolBarLayout = QHBoxLayout()
        self.fontCombo = QFontComboBox()
        self.fontCombo.currentFontChanged.connect(self.currentFontChanged)

        self.fontSizeCombo = QComboBox()
        self.fontSizeCombo.setEditable(True)
        for i in range(8, 30, 2):
            self.fontSizeCombo.addItem(str(i))
        validator = QIntValidator(2, 64, self)
        self.fontSizeCombo.setValidator(validator)
        self.fontSizeCombo.currentIndexChanged.connect(self.fontSizeChanged)

        self.fontColorToolButton = QToolButton()
        self.fontColorToolButton.setPopupMode(QToolButton.MenuButtonPopup)
        self.fontColorToolButton.setMenu(
            self.createColorMenu(self.textColorChanged, Qt.black))
        self.textAction = self.fontColorToolButton.menu().defaultAction()
        self.fontColorToolButton.setIcon(
            self.createColorToolButtonIcon(self.home_path + '/resource/images/skill_editor/textpointer.png', Qt.black))
        self.fontColorToolButton.setAutoFillBackground(True)
        self.fontColorToolButton.clicked.connect(self.textButtonTriggered)

        self.fillColorToolButton = QToolButton()
        self.fillColorToolButton.setPopupMode(QToolButton.MenuButtonPopup)
        self.fillColorToolButton.setMenu(
            self.createColorMenu(self.itemColorChanged, Qt.white))
        self.fillAction = self.fillColorToolButton.menu().defaultAction()
        self.fillColorToolButton.setIcon(
            self.createColorToolButtonIcon(self.home_path + '/resource/images/skill_editor/floodfill.png', Qt.white))
        self.fillColorToolButton.clicked.connect(self.fillButtonTriggered)

        self.lineColorToolButton = QToolButton()
        self.lineColorToolButton.setPopupMode(QToolButton.MenuButtonPopup)
        self.lineColorToolButton.setMenu(
            self.createColorMenu(self.lineColorChanged, Qt.black))
        self.lineAction = self.lineColorToolButton.menu().defaultAction()
        self.lineColorToolButton.setIcon(
            self.createColorToolButtonIcon(self.home_path + '/resource/images/skill_editor/linecolor.png', Qt.black))
        self.lineColorToolButton.clicked.connect(self.lineButtonTriggered)

        self.txtBoldButton = QToolButton()
        self.txtBoldButton.setCheckable(True)
        self.txtBoldButton.setChecked(False)
        self.txtBoldButton.setIcon(QIcon(self.home_path + '/resource/images/skill_editor/bold.png'))
        self.txtItalicButton = QToolButton()
        self.txtItalicButton.setCheckable(True)
        self.txtItalicButton.setChecked(False)
        self.txtItalicButton.setIcon(QIcon(self.home_path + '/resource/images/skill_editor/italic.png'))
        self.txtUnderlineButton = QToolButton()
        self.txtUnderlineButton.setCheckable(True)
        self.txtUnderlineButton.setChecked(False)
        self.txtUnderlineButton.setIcon(QIcon(self.home_path + '/resource/images/skill_editor/underline.png'))

        self.textToolBarLayout = QtWidgets.QHBoxLayout()
        self.textToolBarLayout.addWidget(self.fontCombo)
        self.textToolBarLayout.addWidget(self.fontSizeCombo)
        self.textToolBarLayout.addWidget(self.txtBoldButton)
        self.textToolBarLayout.addWidget(self.txtItalicButton)
        self.textToolBarLayout.addWidget(self.txtUnderlineButton)

        self.colorToolBarLayout = QtWidgets.QHBoxLayout()
        self.colorToolBarLayout.addWidget(self.fontColorToolButton)
        self.colorToolBarLayout.addWidget(self.fillColorToolButton)
        self.colorToolBarLayout.addWidget(self.lineColorToolButton)

        pointerButton = QToolButton()
        pointerButton.setCheckable(True)
        pointerButton.setChecked(True)
        pointerButton.setIcon(QIcon(self.home_path + '/resource/images/skill_editor/pointer.png'))
        linePointerButton = QToolButton()
        linePointerButton.setCheckable(True)
        linePointerButton.setIcon(QIcon(self.home_path + '/resource/images/skill_editor/linepointer.png'))

        self.txtPropertyGroup = QButtonGroup()
        self.txtPropertyGroup.addButton(self.txtBoldButton, DiagramScene.SetTxtBold)
        self.txtPropertyGroup.addButton(self.txtItalicButton, DiagramScene.SetTxtItalic)
        self.txtPropertyGroup.addButton(self.txtUnderlineButton, DiagramScene.SetTxtUnderline)
        self.txtPropertyGroup.buttonClicked.connect(self.txtPropertyGroupClicked)

        self.pointerTypeGroup = QButtonGroup()
        self.pointerTypeGroup.addButton(pointerButton, DiagramScene.MoveItem)
        self.pointerTypeGroup.addButton(linePointerButton, DiagramScene.InsertLine)
        # self.pointerTypeGroup.buttonClicked[int].connect(self.pointerGroupClicked)
        self.pointerTypeGroup.buttonClicked.connect(self.pointerGroupClicked)

        self.sceneScaleCombo = QComboBox()
        self.sceneScaleCombo.addItems(["50%", "75%", "100%", "125%", "150%"])
        self.sceneScaleCombo.setCurrentIndex(2)
        #self.sceneScaleCombo.currentIndexChanged[str].connect(self.sceneScaleChanged)
        self.sceneScaleCombo.currentIndexChanged.connect(self.sceneScaleChanged)

        self.pointerToolbarLayout = QHBoxLayout()
        self.pointerToolbarLayout.addWidget(pointerButton)
        self.pointerToolbarLayout.addWidget(linePointerButton)
        self.pointerToolbarLayout.addWidget(self.sceneScaleCombo)

        self.ToolBarLayout.addLayout(self.textToolBarLayout)
        self.ToolBarLayout.addLayout(self.colorToolBarLayout)
        self.ToolBarLayout.addLayout(self.pointerToolbarLayout)

    def createBackgroundCellWidget(self, text, image):
        button = QToolButton()
        button.setText(text)
        button.setIcon(QIcon(image))
        button.setIconSize(QSize(50, 50))
        button.setCheckable(True)
        self.backgroundButtonGroup.addButton(button)

        layout = QGridLayout()
        layout.addWidget(button, 0, 0, Qt.AlignHCenter)
        layout.addWidget(QLabel(text), 1, 0, Qt.AlignCenter)

        widget = QWidget()
        widget.setLayout(layout)

        return widget

    def createCellWidget(self, text, diagramType):
        item = DiagramItem(diagramType, self.itemMenu)
        print("creating widget type:", diagramType)
        icon = QIcon(item.image())

        button = QToolButton()
        button.setIcon(icon)
        button.setIconSize(QSize(32, 32))
        button.setCheckable(True)
        self.buttonGroup.addButton(button, diagramType)

        layout = QGridLayout()
        layout.addWidget(button, 0, 0, Qt.AlignHCenter)
        layout.addWidget(QLabel(text), 1, 0, Qt.AlignCenter)

        widget = QWidget()
        widget.setLayout(layout)

        return widget

    def createColorMenu(self, slot, defaultColor):
        colors = [Qt.black, Qt.white, Qt.red, Qt.blue, Qt.yellow]
        names = ["black", "white", "red", "blue", "yellow"]

        colorMenu = QMenu(self)
        for color, name in zip(colors, names):
            action = QAction(self.createColorIcon(color), name, self, triggered=slot)
            action.setData(QColor(color))
            colorMenu.addAction(action)
            if color == defaultColor:
                colorMenu.setDefaultAction(action)
        return colorMenu

    def createColorToolButtonIcon(self, imageFile, color):
        pixmap = QPixmap(50, 80)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        image = QPixmap(imageFile)
        target = QRect(0, 0, 50, 60)
        source = QRect(0, 0, 42, 42)
        painter.fillRect(QRect(0, 60, 50, 80), color)
        painter.drawPixmap(target, image, source)
        painter.end()

        return QIcon(pixmap)

    def createColorIcon(self, color):
        pixmap = QPixmap(20, 20)
        painter = QPainter(pixmap)
        painter.setPen(Qt.NoPen)
        painter.fillRect(QRect(0, 0, 20, 20), color)
        painter.end()

        return QIcon(pixmap)