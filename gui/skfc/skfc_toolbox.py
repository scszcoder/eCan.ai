from PySide6.QtCore import QSize
from PySide6.QtGui import Qt, QIcon, QPixmap, QBrush, QPainter, QPen
from PySide6.QtWidgets import QToolBox, QGraphicsView, QWidget, QButtonGroup, QGridLayout, QSizePolicy, QToolButton, \
    QLabel

from skfc.diagram_item_normal import DiagramNormalItem
from skfc.skfc_scene import SkFCScene
from config.app_info import app_info


class SkFCToolBox(QToolBox):
    InsertTextButton = 10

    def __init__(self, skfc_scene, skfc_view, parent=None):
        super(SkFCToolBox, self).__init__(parent)

        self.skfc_scene: SkFCScene = skfc_scene
        self.skfc_view: QGraphicsView = skfc_view
        self.parent: QWidget = parent
        self.home_path = app_info.app_home_path

        self.diagram_button_group = QButtonGroup()
        self.diagram_button_group.setExclusive(False)
        # self.diagram_button_group.buttonClicked[int].connect(self.diagram_button_group_clicked)
        self.diagram_button_group.buttonClicked.connect(self.diagram_button_group_clicked)

        layout = QGridLayout()
        layout.addWidget(self.createCellWidget("Start/End", DiagramNormalItem.StartEnd), 0, 0)
        layout.addWidget(self.createCellWidget("Conditional", DiagramNormalItem.Conditional), 1, 0)
        layout.addWidget(self.createCellWidget("Process", DiagramNormalItem.Step), 2, 0)
        layout.addWidget(self.createCellWidget("Input/Output", DiagramNormalItem.Io), 3, 0)
        layout.addWidget(self.create_text_cell_widget(), 4, 0)

        # layout.setRowStretch(3, 10)
        # layout.setColumnStretch(2, 10)

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
                                            self.home_path + '/resource/images/skill_editor/background2.png'), 1, 0)
        backgroundLayout.addWidget(
            self.createBackgroundCellWidget("Gray Grid",
                                            self.home_path + '/resource/images/skill_editor/background3.png'), 2, 0)
        backgroundLayout.addWidget(
            self.createBackgroundCellWidget("No Grid",
                                            self.home_path + '/resource/images/skill_editor/background4.png'), 3, 0)

        # backgroundLayout.setRowStretch(2, 10)
        # backgroundLayout.setColumnStretch(2, 10)

        background_widget = QWidget()
        background_widget.setLayout(backgroundLayout)

        # toolbox = QToolBox()
        self.setSizePolicy(QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Ignored))
        self.setMinimumWidth(diagram_item_widget.sizeHint().width())
        self.addItem(diagram_item_widget, "Basic Flowchart Shapes")
        self.addItem(background_widget, "Backgrounds")

    def diagram_button_group_clicked(self, button):
        print("skfc toolbox button group clicked:", self.diagram_button_group.id(button))
        buttons = self.diagram_button_group.buttons()
        for mbutton in buttons:
            #if self.diagram_button_group.button(id) != mbutton:
            if button != mbutton:
                button.setChecked(False)

        #if id == self.InsertTextButton:
        if self.diagram_button_group.id(button) == self.InsertTextButton:
            self.skfc_scene.setMode(SkFCScene.InsertText)
        else:
            #self.scene.setItemType(id)
            self.skfc_scene.setItemType(self.diagram_button_group.id(button))
            self.skfc_scene.setMode(SkFCScene.InsertItem)

    def background_button_group_clicked(self, button):
        buttons = self.background_button_group.buttons()
        for myButton in buttons:
            if myButton != button:
                button.setChecked(False)

        text = button.text()
        if text == "Blue Grid":
            self.skfc_scene.setBackgroundBrush(QBrush(QPixmap(self.home_path + '/resource/images/skill_editor/background1.png')))
        elif text == "White Grid":
            self.skfc_scene.setBackgroundBrush(QBrush(QPixmap(self.home_path + '/resource/images/skill_editor/background2.png')))
        elif text == "Gray Grid":
            self.skfc_scene.setBackgroundBrush(QBrush(QPixmap(self.home_path + '/resource/images/skill_editor/background3.png')))
        else:
            self.skfc_scene.setBackgroundBrush(QBrush(QPixmap(self.home_path + '/resource/images/skill_editor/background4.png')))

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
        textLayout.addWidget(textButton, 0, 0, Qt.AlignmentFlag.AlignHCenter)
        textLayout.addWidget(QLabel("Text"), 1, 0, Qt.AlignmentFlag.AlignCenter)

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
        layout.addWidget(button, 0, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(QLabel(text), 1, 0, Qt.AlignmentFlag.AlignCenter)

        widget = QWidget()
        widget.setLayout(layout)

        return widget

    def createCellWidget(self, text, diagram_type):
        # item = DiagramItem(diagramType, )
        print("pyq skfc creating widget type:", diagram_type)
        icon = QIcon(self.diagram_icon_image(diagram_type))

        button = QToolButton()
        button.setIcon(icon)
        button.setIconSize(QSize(32, 32))
        button.setCheckable(True)
        self.diagram_button_group.addButton(button, diagram_type)

        layout = QGridLayout()
        layout.addWidget(button, 0, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(QLabel(text), 1, 0, Qt.AlignmentFlag.AlignCenter)

        widget = QWidget()
        widget.setLayout(layout)

        return widget

    def diagram_icon_image(self, diagram_type):
        pixmap = QPixmap(250, 250)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setPen(QPen(Qt.GlobalColor.black, 8))
        painter.translate(125, 125)
        painter.drawPolyline(DiagramNormalItem.create_item_polygon(diagram_type))

        return pixmap
