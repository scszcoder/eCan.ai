from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QFont
from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QTableWidget, QLabel, QTableWidgetItem, QGraphicsView, \
    QHBoxLayout, QPushButton, QFrame, QBoxLayout, QLineEdit, QToolButton, QSizePolicy, QAbstractItemView, QHeaderView

from skfc.skfc_scene import SkFCScene
from config.app_info import app_info


class SkFCInfoBox(QFrame):

    def __init__(self, skfc_scene, skfc_view, parent=None):
        super(SkFCInfoBox, self).__init__(parent)
        self.setFrameStyle(QFrame.Shape.Panel | QFrame.Shadow.Plain)
        self.setLineWidth(0)

        self.skfc_scene: SkFCScene = skfc_scene
        self.skfc_view: QGraphicsView = skfc_view
        self.parent: QWidget = parent
        self.home_path = app_info.app_home_path

        # self.toggle_btn_collapse = QToolButton()
        # self.toggle_btn_collapse.setIcon(QIcon(app_info.app_resources_path + "/images/icons/skfc_collapse.png"))  # 设置图标的路径
        # self.toggle_btn_collapse.setCheckable(True)
        # self.toggle_btn_collapse.setChecked(False)
        # self.toggle_btn_collapse.clicked.connect(self.toggle_collapse)
        #
        # self.toggle_btn_expand = QToolButton()
        # self.toggle_btn_expand.setIcon(QIcon(app_info.app_resources_path + "/images/icons/skfc_expand.png"))  # 设置图标的路径
        # self.toggle_btn_expand.setCheckable(True)
        # self.toggle_btn_expand.setChecked(False)
        # self.toggle_btn_expand.setVisible(False)
        # self.toggle_btn_expand.clicked.connect(self.toggle_expand)

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
        self.basic_info_widget = QTableWidget(2, 2)
        self.basic_info_widget.horizontalHeader().setVisible(False)
        self.basic_info_widget.verticalHeader().setVisible(False)
        self.basic_info_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.basic_info_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)  # 水平方向自动拉伸列宽
        # self.basic_info_widget.setSizeAdjustPolicy(QTableWidget.SizeAdjustPolicy.AdjustToContents)  # 根据内容自动调整大小
        # self.basic_info_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)  # 设置拉伸策略，占满父组件

        self.basic_info_widget.setCellWidget(0, 0, QLabel("Skill Name"))
        self.basic_info_widget.setCellWidget(0, 1, self.basic_info_skname)
        self.basic_info_widget.setCellWidget(1, 0, QLabel("Location"))
        self.basic_info_widget.setCellWidget(1, 1, self.basic_info_sklocation)

        self.properties_widget = QTableWidget(1, 2)
        self.properties_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.properties_widget.verticalHeader().setVisible(False)
        self.properties_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)  # 水平方向自动拉伸列宽
        # self.properties_widget.setSizeAdjustPolicy(QTableWidget.SizeAdjustPolicy.AdjustToContents)  # 根据内容自动调整大小
        # self.properties_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)  # 设置拉伸策略，占满父组件

        self.properties_widget.setHorizontalHeaderLabels(["Property", "Value"])
        self.properties_widget.horizontalHeader().setFont(QFont('Arial', 14))
        self.properties_widget.setItem(0, 0, QTableWidgetItem("John Doe"))
        self.properties_widget.setItem(0, 1, QTableWidgetItem("30"))

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        # main_layout.addWidget(self.toggle_btn_expand)
        main_layout.addWidget(self.panel_title_widget)
        main_layout.addWidget(self.basic_info_widget, 1)
        main_layout.addWidget(self.properties_widget, 2)

        # self.setSizePolicy(QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Ignored))
        # self.setMinimumWidth(self.panel_title_widget.sizeHint().width())

    # def toggle_collapse(self):
    #     # self.panel_title_widget.hide()
    #     # self.basic_info_widget.hide()
    #     # self.properties_widget.hide()
    #     #
    #     # self.toggle_btn_expand.show()
    #     # self.adjustSize()
    #     # self.setVisible(False)
    #     self.parent.vsplitter_body.setSizes([0, 2])
    #
    # def toggle_expand(self):
    #     self.panel_title_widget.show()
    #     self.basic_info_widget.show()
    #     self.properties_widget.show()
    #
    #     self.toggle_btn_expand.hide()
    #     self.adjustSize()
