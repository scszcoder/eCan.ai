from enum import Enum

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QFont, QPainter, QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QLabel, QTableWidgetItem, QGraphicsView, \
    QHBoxLayout, QFrame, QLineEdit, QHeaderView, QComboBox, QCheckBox, QApplication

from gui.skfc.diagram_item_normal import DiagramNormalItem
from skfc.skfc_base import EnumSkType
from skfc.skfc_scene import SkFCScene
from config.app_info import app_info
from skill.steps.enum_step_type import EnumStepType
from skill.steps.step_base import StepBase
from skill.steps.step_check_condition import StepCheckCondition
from skill.steps.step_fill_data import StepFillData
from skill.steps.step_stub import StepStub
from skill.steps.step_wait import StepWait

PROPS_COLUMN_COUNT = 2
STEP_ATTR_KEY = "step_attr_key"


class SKInfo:
    def __init__(self, skname="", sktype=EnumSkType.Sub.value, os="win", version="1.0", author="AIPPS LLC", skid="", description=""):
        self.skname = skname
        self.sktype = sktype
        self.os = os
        self.version = version
        self.author = author
        self.skid = skid
        self.description = description

    @classmethod
    def from_dict(cls, obj_dict):
        sk_info = SKInfo()
        for key, value in dict(obj_dict).items():
            setattr(sk_info, key, value)

        return sk_info

    def get_skid(self):
        return self.skid


# class SwitchButton(QWidget):
#     stateChanged = Signal(bool)
#
#     def __init__(self, parent=None):
#         super().__init__(parent)
#         self.setFixedSize(64, 24)
#         self._checked = False
#
#     def paintEvent(self, event):
#         painter = QPainter(self)
#         painter.setRenderHint(QPainter.Antialiasing)
#
#         # 绘制背景
#         bg_color = QColor(0, 255, 0) if self._checked else QColor(100, 100, 100)
#         painter.setBrush(bg_color)
#         painter.drawRoundedRect(0, 0, self.width(), self.height(), 15, 15)
#
#         # 绘制滑块
#         slider_color = QColor(255, 255, 255) if self._checked else QColor(200, 200, 200)
#         slider_x = self.width() - 23 if self._checked else 3
#         painter.setBrush(slider_color)
#         painter.drawEllipse(slider_x, 3, 18, 18)
#
#     def mousePressEvent(self, event):
#         self.setChecked(not self._checked)
#         self.update()
#
#     def isChecked(self):
#         return self._checked
#
#     def setChecked(self, checked):
#         if self._checked != checked:
#             self._checked = checked
#             self.stateChanged.emit(checked)
#             self.update()


class SkFCInfoBox(QFrame):

    def __init__(self, skfc_scene, skfc_view, parent=None):
        super(SkFCInfoBox, self).__init__(parent)
        self.setFrameStyle(QFrame.Shape.Panel | QFrame.Shadow.Plain)
        self.setLineWidth(0)

        self.skfc_scene: SkFCScene = skfc_scene
        self.skfc_view: QGraphicsView = skfc_view
        self.parent: QWidget = parent
        self.home_path = app_info.app_home_path
        self.current_diagram_item = None

        self.panel_title_label = QLabel("Basic Information")
        self.panel_title_layout = QHBoxLayout()
        self.panel_title_layout.setContentsMargins(0, 0, 0, 0)
        self.panel_title_layout.addWidget(self.panel_title_label)
        # self.panel_title_layout.addWidget(self.toggle_btn_collapse)

        self.panel_title_widget = QWidget()
        self.panel_title_widget.setLayout(self.panel_title_layout)

        self.basic_info_skname = QLineEdit()
        # self.basic_info_skname.setPlaceholderText("Skill Name")
        # self.basic_info_sklocation = QLineEdit()
        # self.basic_info_sklocation.setPlaceholderText("Location")
        self.basic_info_skos = QLineEdit()
        self.basic_info_skversion = QLineEdit()
        self.basic_info_skauthor = QLineEdit()
        self.basic_info_skid = QLineEdit()
        self.basic_info_skdesp = QLineEdit()

        self.basic_info_sktype = QComboBox()
        self.basic_info_sktype.addItem(QApplication.translate("QComboBox", "Main Skill"), EnumSkType.Main.value)
        self.basic_info_sktype.addItem(QApplication.translate("QComboBox", "Sub Skill"), EnumSkType.Sub.value)
        self.basic_info_sktype.activated.connect(self.basic_info_sktype_activated)

        self.basic_info_table = QTableWidget(7, 2)
        self.basic_info_table.horizontalHeader().setVisible(False)
        self.basic_info_table.verticalHeader().setVisible(False)
        self.basic_info_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.basic_info_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)  # 水平方向自动拉伸列宽
        # self.basic_info_table.setSizeAdjustPolicy(QTableWidget.SizeAdjustPolicy.AdjustToContents)  # 根据内容自动调整大小
        # self.basic_info_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)  # 设置拉伸策略，占满父组件

        self.basic_info_table.setCellWidget(0, 0, QLabel("Skill Name"))
        self.basic_info_table.setCellWidget(0, 1, self.basic_info_skname)
        self.basic_info_table.setCellWidget(1, 0, QLabel("Skill Type"))
        self.basic_info_table.setCellWidget(1, 1, self.basic_info_sktype)
        self.basic_info_table.setCellWidget(2, 0, QLabel("SkId"))
        self.basic_info_table.setCellWidget(2, 1, self.basic_info_skid)
        self.basic_info_table.setCellWidget(3, 0, QLabel("OS"))
        self.basic_info_table.setCellWidget(3, 1, self.basic_info_skos)
        self.basic_info_table.setCellWidget(4, 0, QLabel("Version"))
        self.basic_info_table.setCellWidget(4, 1, self.basic_info_skversion)
        self.basic_info_table.setCellWidget(5, 0, QLabel("Author"))
        self.basic_info_table.setCellWidget(5, 1, self.basic_info_skauthor)
        self.basic_info_table.setCellWidget(6, 0, QLabel("Description"))
        self.basic_info_table.setCellWidget(6, 1, self.basic_info_skdesp)

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
        self.init_qline_edit(SKInfo())

    def to_dict(self):
        sk_info = self.get_skill_info()

        return sk_info.__dict__

    def from_json(self, sk_info_dict: dict):
        sk_info = self.gen_sk_info(sk_info_dict)
        if sk_info:
            self.init_qline_edit(sk_info)

    @staticmethod
    def gen_sk_info(sk_info_dict: dict):
        if sk_info_dict is not None:
            return SKInfo.from_dict(sk_info_dict)
        return None

    def init_qline_edit(self, sk_info: SKInfo):
        self.basic_info_skname.setText(sk_info.skname)
        index = self.basic_info_sktype.findData(sk_info.sktype)
        if index >= 0:
            self.basic_info_sktype.setCurrentIndex(index)
        self.basic_info_skos.setText(sk_info.os)
        self.basic_info_skversion.setText(sk_info.version)
        self.basic_info_skauthor.setText(sk_info.author)
        self.basic_info_skid.setText(sk_info.skid)
        self.basic_info_skdesp.setText(sk_info.description)

    def get_skill_info(self) -> SKInfo:
        skname = self.basic_info_skname.text()
        sktype = self.basic_info_sktype.currentData()
        skid = self.basic_info_skid.text()
        os = self.basic_info_skos.text()
        version = self.basic_info_skversion.text()
        author = self.basic_info_skauthor.text()
        desp = self.basic_info_skdesp.text()

        sk_info = SKInfo(skname, sktype, os, version, author, skid, desp)

        return sk_info

    def basic_info_sktype_activated(self):
        value = self.basic_info_sktype.currentData()
        text = self.basic_info_sktype.currentText()

        print(f"text: {text}, value: {value}")

    def convert_field_name(self, text):
        return ' '.join(w.capitalize() for w in text.split('_'))

    def create_step_obj(self, diagram_type):
        if diagram_type == DiagramNormalItem.StartEnd:
            return StepStub()
        elif diagram_type == DiagramNormalItem.Conditional:
            return StepCheckCondition()
        elif diagram_type == DiagramNormalItem.Step:
            return StepWait()
        elif diagram_type == DiagramNormalItem.Io:
            return StepFillData()

    def show_diagram_item_step_attrs(self, diagram_item: DiagramNormalItem):
        diagram_type = diagram_item.diagram_type
        if diagram_item.step is None:
            diagram_item.step = self.create_step_obj(diagram_type)

        self.current_diagram_item = diagram_item

        attrs = diagram_item.step.gen_need_show_attrs()
        self.attrs_table.setRowCount(len(attrs))

        for row, (key, value) in enumerate(attrs.items()):
            # print(f"Row: {row}, Key: {key}, Value: {value}")
            item_label = QLabel(self.convert_field_name(key))
            item_widget = self.create_attrs_cell_widget(diagram_type, diagram_item.step, key, value)

            self.attrs_table.setCellWidget(row, 0, item_label)
            self.attrs_table.setCellWidget(row, 1, item_widget)

    def create_attrs_cell_widget(self, diagram_type, step, step_attr_key, step_attrs_value):
        # Step type attr field
        if step_attr_key == "type":
            widget = QComboBox()
            for item in self.create_step_type_attr_items(diagram_type):
                widget.addItem(item)
            widget.setCurrentText(step_attrs_value)
            widget.currentTextChanged.connect(self.step_attrs_type_cmb_changed)
        else:  # normal attrs field
            if isinstance(step_attrs_value, Enum):
                # print(f"step enum attrs: key {step_attr_key}= {step_attrs_value.value}")
                filtered_enum_items = step.filter_enum_show_items(self.get_skill_info().sktype, type(step_attrs_value))
                widget = QComboBox()
                for name, member in filtered_enum_items:
                    widget.addItem(member.value)
                widget.setCurrentText(step_attrs_value.value)
                widget.currentTextChanged.connect(self.step_attrs_normal_cmb_changed)
            elif isinstance(step_attrs_value, bool):
                widget = QCheckBox('', self)
                # widget.move(20, 20)
                widget.stateChanged.connect(self.step_attrs_toggle_state_changed)
            else:
                widget = QLineEdit()
                widget.setText(str(step_attrs_value))
                widget.textChanged.connect(self.step_attrs_text_changed)

        widget.setProperty(STEP_ATTR_KEY, step_attr_key)
        # print(f"create field: {step_attr_key}; cell widget {widget}")
        return widget

    def create_step_type_attr_items(self, diagram_type):
        types = []
        for key, value in EnumStepType.items():
            if diagram_type == DiagramNormalItem.StartEnd:
                if key in EnumStepType.belong_start_end_step_type_keys():
                    types.append(key)
            elif diagram_type == DiagramNormalItem.Conditional:
                if key in EnumStepType.belong_condition_step_type_keys():
                    types.append(key)
            elif diagram_type == DiagramNormalItem.Step:
                if key in EnumStepType.belong_process_step_type_keys():
                    types.append(key)
            elif diagram_type == DiagramNormalItem.Io:
                if key in EnumStepType.belong_io_step_type_keys():
                    types.append(key)

        return types

    def step_attrs_type_cmb_changed(self, step_key):
        print(f"step_key: {step_key}")
        self.current_diagram_item.step = EnumStepType.gen_step_obj(step_key)
        self.show_diagram_item_step_attrs(self.current_diagram_item)

    def step_attrs_normal_cmb_changed(self, text):
        print("cmb changed ", text, self.sender())
        step: StepBase = self.current_diagram_item.step
        step.set_attr_value(self.sender().property(STEP_ATTR_KEY), text)

    def step_attrs_toggle_state_changed(self, state):
        print('SwitchButton state changed:', state, self.sender())
        step: StepBase = self.current_diagram_item.step
        step.set_attr_value(self.sender().property(STEP_ATTR_KEY), True if state == 2 else False)

    def step_attrs_text_changed(self, text):
        print("text changed: ", text, self.sender())
        step: StepBase = self.current_diagram_item.step
        step.set_attr_value(self.sender().property(STEP_ATTR_KEY), text)
