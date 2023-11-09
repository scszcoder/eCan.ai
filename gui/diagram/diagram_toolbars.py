from PySide6.QtCore import (QRect, Qt)
from PySide6.QtGui import (QAction, QColor, QFont, QIcon, QIntValidator, QPainter, QPixmap)
from PySide6.QtWidgets import QButtonGroup, QComboBox, QFontComboBox, QGraphicsView, \
                            QHBoxLayout, QMenu, QToolButton, QWidget
from gui.diagram.diagram_scene import DiagramScene
from config.app_info import app_info


class DiagramToolBars(QHBoxLayout):
    def __init__(self, diagram_scene, drawing_view, parent=None):
        super(DiagramToolBars, self).__init__(parent)

        self.diagram_scene: DiagramScene = diagram_scene
        self.drawing_view: QGraphicsView = drawing_view
        self.parent: QWidget = parent
        self.home_path = app_info.app_home_path

        # self.toolBarLayout = QHBoxLayout()
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
        self.fontColorToolButton.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.fontColorToolButton.setMenu(
            self.createColorMenu(self.textColorChanged, Qt.black, self.fontColorToolButton))
        self.textAction = self.fontColorToolButton.menu().defaultAction()
        self.fontColorToolButton.setIcon(
            self.createColorToolButtonIcon(self.home_path + '/resource/images/skill_editor/textpointer.png', Qt.black))
        self.fontColorToolButton.setAutoFillBackground(True)
        self.fontColorToolButton.clicked.connect(self.textButtonTriggered)

        self.fillColorToolButton = QToolButton()
        self.fillColorToolButton.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.fillColorToolButton.setMenu(
            self.createColorMenu(self.itemColorChanged, Qt.white, self.fillColorToolButton))
        self.fillAction = self.fillColorToolButton.menu().defaultAction()
        self.fillColorToolButton.setIcon(
            self.createColorToolButtonIcon(self.home_path + '/resource/images/skill_editor/floodfill.png', Qt.white))
        self.fillColorToolButton.clicked.connect(self.fillButtonTriggered)

        self.lineColorToolButton = QToolButton()
        self.lineColorToolButton.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.lineColorToolButton.setMenu(
            self.createColorMenu(self.lineColorChanged, Qt.black, self.lineColorToolButton))
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

        self.textToolBarLayout = QHBoxLayout()
        self.textToolBarLayout.addWidget(self.fontCombo)
        self.textToolBarLayout.addWidget(self.fontSizeCombo)
        self.textToolBarLayout.addWidget(self.txtBoldButton)
        self.textToolBarLayout.addWidget(self.txtItalicButton)
        self.textToolBarLayout.addWidget(self.txtUnderlineButton)

        self.colorToolBarLayout = QHBoxLayout()
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
        # self.sceneScaleCombo.currentIndexChanged[str].connect(self.sceneScaleChanged)
        self.sceneScaleCombo.currentIndexChanged.connect(self.sceneScaleChanged)

        self.pointerToolbarLayout = QHBoxLayout()
        self.pointerToolbarLayout.addWidget(pointerButton)
        self.pointerToolbarLayout.addWidget(linePointerButton)
        self.pointerToolbarLayout.addWidget(self.sceneScaleCombo)

        self.addLayout(self.textToolBarLayout)
        self.addLayout(self.colorToolBarLayout)
        self.addLayout(self.pointerToolbarLayout)

    def pointerGroupClicked(self, i):
        self.diagram_scene.setMode(self.pointerTypeGroup.checkedId())

    def txtPropertyGroupClicked(self, i):
        self.handleFontChange()

    def textButtonTriggered(self):
        self.diagram_scene.setTextColor(QColor(self.textAction.data()))

    def fillButtonTriggered(self):
        self.diagram_scene.setItemColor(QColor(self.fillAction.data()))

    def lineButtonTriggered(self):
        self.diagram_scene.setLineColor(QColor(self.lineAction.data()))

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
        #oldMatrix = self.drawing_view.matrix()
        oldMatrix = self.drawing_view.transform()
        # self.drawing_view.resetMatrix()
        self.drawing_view.resetTransform()
        self.drawing_view.translate(oldMatrix.dx(), oldMatrix.dy())
        self.drawing_view.scale(newScale, newScale)

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

    def createColorMenu(self, slot, defaultColor, parent):
        colors = [Qt.black, Qt.white, Qt.red, Qt.blue, Qt.yellow]
        names = ["black", "white", "red", "blue", "yellow"]

        colorMenu = QMenu(parent)
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

        self.diagram_scene.setFont(font)
