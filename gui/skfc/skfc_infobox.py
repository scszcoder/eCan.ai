from enum import Enum

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QFont
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QLabel, QTableWidgetItem, QGraphicsView, \
    QHBoxLayout, QFrame, QLineEdit, QHeaderView, QComboBox

from skfc.diagram_item_normal import DiagramNormalItem
from skfc.skfc_scene import SkFCScene
from config.app_info import app_info
from skill.steps.enum_step_type import EnumStepType
from skill.steps.step_base import StepBase
from bot.readSkill import vicrop
from skill.steps.step_check_condition import StepCheckCondition
from skill.steps.step_fill_data import StepFillData
from skill.steps.step_stub import StepStub

PROPS_COLUMN_COUNT = 2


class SkFCInfoBox(QFrame):

    def __init__(self, skfc_scene, skfc_view, parent=None):
        super(SkFCInfoBox, self).__init__(parent)
        self.setFrameStyle(QFrame.Shape.Panel | QFrame.Shadow.Plain)
        self.setLineWidth(0)

        self.skfc_scene: SkFCScene = skfc_scene
        self.skfc_view: QGraphicsView = skfc_view
        self.parent: QWidget = parent
        self.home_path = app_info.app_home_path

        self.panel_title_label = QLabel("Basic Information")
        self.panel_title_layout = QHBoxLayout()
        self.panel_title_layout.setContentsMargins(0, 0, 0, 0)
        self.panel_title_layout.addWidget(self.panel_title_label)
        # self.panel_title_layout.addWidget(self.toggle_btn_collapse)

        self.panel_title_widget = QWidget()
        self.panel_title_widget.setLayout(self.panel_title_layout)

        self.basic_info_skname = QLineEdit()
        self.basic_info_skname.setPlaceholderText("Skill Name")
        self.basic_info_sklocation = QLineEdit()
        self.basic_info_sklocation.setPlaceholderText("Location")
        self.basic_info_table = QTableWidget(2, 2)
        self.basic_info_table.horizontalHeader().setVisible(False)
        self.basic_info_table.verticalHeader().setVisible(False)
        self.basic_info_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.basic_info_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)  # 水平方向自动拉伸列宽
        # self.basic_info_table.setSizeAdjustPolicy(QTableWidget.SizeAdjustPolicy.AdjustToContents)  # 根据内容自动调整大小
        # self.basic_info_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)  # 设置拉伸策略，占满父组件

        self.basic_info_table.setCellWidget(0, 0, QLabel("Skill Name"))
        self.basic_info_table.setCellWidget(0, 1, self.basic_info_skname)
        self.basic_info_table.setCellWidget(1, 0, QLabel("Location"))
        self.basic_info_table.setCellWidget(1, 1, self.basic_info_sklocation)

        self.attrs_table = QTableWidget(0, PROPS_COLUMN_COUNT)
        self.attrs_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.attrs_table.verticalHeader().setVisible(False)
        self.attrs_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)  # 水平方向自动拉伸列宽
        # self.props_table.setSizeAdjustPolicy(QTableWidget.SizeAdjustPolicy.AdjustToContents)  # 根据内容自动调整大小
        # self.props_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)  # 设置拉伸策略，占满父组件

        self.attrs_table.setHorizontalHeaderLabels(["Property", "Value"])
        self.attrs_table.horizontalHeader().setFont(QFont('Arial', 14))

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.panel_title_widget)
        main_layout.addWidget(self.basic_info_table, 1)
        main_layout.addWidget(self.attrs_table, 2)

        # self.setSizePolicy(QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Ignored))
        # self.setMinimumWidth(self.panel_title_widget.sizeHint().width())

    def convert_field_name(self, text):
        return ' '.join(w.capitalize() for w in text.split('_'))

    def create_step_obj(self, diagram_type):
        if diagram_type == DiagramNormalItem.StartEnd:
            return StepStub()
        elif diagram_type == DiagramNormalItem.Conditional:
            return StepCheckCondition()
        elif diagram_type == DiagramNormalItem.Step:
            return StepBase()
        elif diagram_type == DiagramNormalItem.Io:
            return StepFillData()

    def show_item_step_attrs(self, diagram_item: DiagramNormalItem):
        self.diagram_item = diagram_item
        diagram_type = diagram_item.diagram_type
        step = diagram_item.step
        if step is None:
            step = self.create_step_obj(diagram_type)

        attrs = step.gen_attrs()
        self.attrs_table.setRowCount(len(attrs))

        for row, (key, value) in enumerate(attrs.items()):
            print(f"Row: {row}, Key: {key}, Value: {value}")
            self.attrs_table.setCellWidget(row, 0, QLabel(self.convert_field_name(key)))
            self.attrs_table.setCellWidget(row, 1, self.create_props_cell_widget(diagram_type, key, value))

    def create_props_cell_widget(self, diagram_type, step_props_key, step_props_value):
        widget = None
        if step_props_key == "type":
            self.step_type_sel = QComboBox()
            for item in self.create_step_type_items(diagram_type):
                self.step_type_sel.addItem(item)
            self.step_type_sel.setCurrentText(step_props_value)
            self.step_type_sel.currentTextChanged.connect(self.step_type_sel_changed)

            widget = self.step_type_sel
        else:
            if isinstance(step_props_value, Enum):
                print(step_props_value)

        return widget

    def create_step_type_items(self, diagram_type):
        types = []
        for key, value in EnumStepType.items():
            if diagram_type == DiagramNormalItem.StartEnd:
                if key == StepStub.TYPE_KEY:
                    types.append(key)
            elif diagram_type == DiagramNormalItem.Conditional:
                types.append(key)
            elif diagram_type == DiagramNormalItem.Step:
                types.append(key)
            elif diagram_type == DiagramNormalItem.Io:
                types.append(key)

        return types

    def step_type_sel_changed(self, step_key):
        print(f"step_key: {step_key}")
        step = EnumStepType.gen_step_obj(step_key)

        self.diagram_item.step = step
        self.show_item_step_attrs(self.diagram_item)




