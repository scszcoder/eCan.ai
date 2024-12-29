import ast
import json
from typing import List

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFont, QStandardItemModel, QStandardItem, QIcon, QAction
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QMainWindow, QFileDialog, QTabWidget, QScrollArea, \
    QVBoxLayout, QLineEdit, QRadioButton, QHBoxLayout, QComboBox, QCheckBox, QListView, QFrame, QMenu, QLabel, \
    QTableView, QMessageBox, QStyledItemDelegate
from bot.ebbot import EBBOT
from common.models import VehicleModel
from gui.tool.MainGUITool import StaticResource



class ComboBoxDelegate(QStyledItemDelegate):
    def __init__(self, parent, items):
        super().__init__(parent)
        self.items = items

    def createEditor(self, parent, option, index):
        combobox = QComboBox(parent)
        combobox.addItems(self.items)
        combobox.currentIndexChanged.connect(lambda: self.commitData.emit(combobox))
        return combobox

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        if value in self.items:
            editor.setCurrentText(value)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.EditRole)


# bot parameters:
# botid,owner,level,levelStart,gender,birthday,interests,location,roles,status,delDate
# note: level is in the format of: "site:level:role,site:level:role....."
#       levelStart is in the format of: "site:birthday:role,site:birthday:role....."
#       role is in the format: site:role, site:role      role can be "buyer"/"seller"/
class BotNewWin(QMainWindow):
    def __init__(self, main_win):
        super(BotNewWin, self).__init__(main_win)
        self.main_win = main_win
        self.newBot = EBBOT(main_win)
        self.vehicleArray = self.findAllVehicle()
        # def __init__(self):
        #     super().__init__()
        self.mainWidget = QWidget()

        self.homepath = self.main_win.homepath

        self.text = QApplication.translate("QWidget", "new bot")
        self.pubpflWidget = QWidget()
        self.prvpflWidget = QWidget()
        self.setngsWidget = QWidget()
        self.statWidget = QWidget()
        self.tabs = QTabWidget()
        self.actionFrame = QFrame()

        self.selected_interest_platform = "Amazon"
        self.selected_interest_main_category = "any"
        self.selected_interest_sub_category1 = "any"
        self.selected_interest_sub_category2 = "any"
        self.selected_interest_sub_category3 = "any"
        self.selected_interest_sub_category4 = "any"
        self.selected_interest_sub_category5 = "any"
        self.selected_vehicle_combo_box = 'NA'
        self.selected_role_platform = "Amazon"
        self.selected_role_level = "Green"
        self.selected_role_role = "Buyer"

        self.fsel = QFileDialog()
        self.mode = "new"

        self.popMenu = QMenu(self)
        self.pop_menu_font = QFont("Helvetica", 10)
        self.popMenu.setFont(self.pop_menu_font)

        self.popMenu.addAction(QAction(QApplication.translate("QAction", "&Edit"), self))
        self.popMenu.addSeparator()
        self.popMenu.addAction(QAction(QApplication.translate("QAction", "&Delete"), self))

        self.roleTableView = QTableView()
        self.roleTableView.resizeColumnsToContents()
        self.roleTableView.resizeRowsToContents()
        self.roleTableModel = QStandardItemModel()
        self.roleTableView.setModel(self.roleTableModel)

        self.roleScrollLabel = QLabel(QApplication.translate("QLabel", "<b style='color:red;'>Roles:</b>"),
                                      alignment=Qt.AlignLeft)

        self.interestTableView = QTableView()
        self.interestTableView.resizeColumnsToContents()
        self.interestTableView.resizeRowsToContents()
        self.interestTableModel = QStandardItemModel()
        self.interestTableView.setModel(self.interestTableModel)

        # 分别为两个TableView创建上下文菜单
        self.roleMenu = self.createContextMenu(self.roleTableView, self.roleTableModel)
        self.interestMenu = self.createContextMenu(self.interestTableView, self.interestTableModel)

        # 安装事件过滤器
        self.roleTableView.installEventFilter(self)
        self.interestTableView.installEventFilter(self)

        self.interestScrollLabel = QLabel(QApplication.translate("QLabel", "Interests:"), alignment=Qt.AlignLeft)

        self.role_save_button = QPushButton(QApplication.translate("QPushButton", "Save Role"))
        self.interest_save_button = QPushButton(QApplication.translate("QPushButton", "Save Interest"))
        self.save_button = QPushButton(QApplication.translate("QPushButton", "Save"))
        self.cancel_button = QPushButton(QApplication.translate("QPushButton", "Cancel"))
        self.text = QLabel(QApplication.translate("QLabel", "Hello World"), alignment=Qt.AlignCenter)

        self.layout = QVBoxLayout(self)
        self.bLayout = QHBoxLayout(self)
        self.bLayout.addWidget(self.cancel_button)
        self.bLayout.addWidget(self.save_button)

        self.pubpflWidget_layout = QVBoxLayout(self)
        self.prvpflWidget_layout = QVBoxLayout(self)
        self.setngsWidget_layout = QVBoxLayout(self)
        self.statWidget_layout = QVBoxLayout(self)

        self.tag_label = QLabel(QApplication.translate("QLabel", "Bot ID:"), alignment=Qt.AlignLeft)
        self.tag_edit = QLineEdit("")
        self.tag_edit.setPlaceholderText(QApplication.translate("QLineEdit", "auto generated bot ID here"))
        self.tag_edit.setReadOnly(True)
        self.icon_label = QLabel(QApplication.translate("QLabel", "Icon Image:"))
        self.icon_path_edit = QLineEdit("")
        self.icon_path_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input icon img file path here"))

        self.icon_fs_button = QPushButton("...")
        self.icon_fs_button.clicked.connect(self.selFile)

        # needs to add icon for better UE

        self.pfn_label = QLabel(QApplication.translate("QLabel", "Pseudo First Name:"), alignment=Qt.AlignLeft)
        self.pfn_edit = QLineEdit()
        self.pfn_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input Pseudo First Name here"))
        self.pln_label = QLabel(QApplication.translate("QLabel", "Pseudo Last Name:"), alignment=Qt.AlignLeft)
        self.pln_edit = QLineEdit()
        self.pln_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input Pseudo Last Name here"))
        self.pnn_label = QLabel(QApplication.translate("QLabel", "Pseudo Nick Name:"), alignment=Qt.AlignLeft)
        self.pnn_edit = QLineEdit()
        self.pnn_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input Pseudo Nick Name here"))
        self.loccity_label = QLabel(QApplication.translate("QLabel", "<b style='color:red;'>Location City:</b>"),
                                    alignment=Qt.AlignLeft)
        self.loccity_edit = QLineEdit()
        self.loccity_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input City here"))
        self.locstate_label = QLabel(QApplication.translate("QLabel", "<b style='color:red;'>Location State:</b>"),
                                     alignment=Qt.AlignLeft)
        self.locstate_edit = QLineEdit()
        self.locstate_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input State here"))
        self.age_label = QLabel(QApplication.translate("QLabel", "Age:"), alignment=Qt.AlignLeft)
        self.age_edit = QLineEdit()
        self.age_edit.setReadOnly(True)
        self.pfn_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input age here"))
        self.vehicle_label = QLabel(QApplication.translate("QLabel", "<b style='color:red;'>Vehicle:</b>"), alignment=Qt.AlignLeft)
        self.vehicle_combo_box = QComboBox()
        self.vehicle_list = []
        for p in self.main_win.vehicles:
            combined_value = f"{p.getOS()}-{p.getName()}-{p.getIP()} {len(p.getBotIds())}"
            self.vehicle_list.append(p.getName())
            item = QApplication.translate("QComboBox", p.getName())
            self.vehicle_combo_box.addItem(item)
            if len(p.bot_ids) > p.CAP:
                index = self.vehicle_combo_box.findText(item)
                if index >= 0:
                    self.vehicle_combo_box.model().item(index).setEnabled(False)
        self.vehicle_combo_box.setCurrentIndex(-1)
        self.vehicle_combo_box.currentTextChanged.connect(self.vehicle_combo_box_changed)

        self.private_attribute_note_label = QLabel(QApplication.translate("QLabel", "<b style='color:Blue;'>Private Attributes will NOT be sent to the cloud, they will ONLY stay on this computer.</b>"), alignment=Qt.AlignLeft)
        self.private_attribute_note_label.setFixedHeight(30)

        self.mf_label = QLabel(QApplication.translate("QLabel", "<b style='color:red;'>Gender:</b>"),
                               alignment=Qt.AlignLeft)

        self.bd_label = QLabel(QApplication.translate("QLabel", "<b style='color:red;'>Birthday:</b>"),
                               alignment=Qt.AlignLeft)
        self.bd_edit = QLineEdit()
        self.bd_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input in YYYY-MM-DD format"))

        self.m_rb = QRadioButton(QApplication.translate("QRadioButton", "Male"))
        self.f_rb = QRadioButton(QApplication.translate("QRadioButton", "Female"))
        self.gna_rb = QRadioButton(QApplication.translate("QRadioButton", "Unknown"))
        self.gna_rb.isChecked()

        self.interest_area_label = QLabel(QApplication.translate("QLabel", "Interests Area:"), alignment=Qt.AlignLeft)
        self.interest_platform_label = QLabel(QApplication.translate("QLabel", "Interests platform:"),
                                              alignment=Qt.AlignLeft)
        self.interest_platform_sel = QComboBox()
        self.static_resource = StaticResource()
        self.interest_platform_sel_list = self.static_resource.SITES
        self.interest_platform_sel_list.insert(0, "any")
        for p in self.interest_platform_sel_list:
            self.interest_platform_sel.addItem(QApplication.translate("QComboBox", p))
        self.interest_platform_sel.currentTextChanged.connect(self.interestPlatformSel_changed)
        self.interest_main_category_label = QLabel(QApplication.translate("QLabel", "Interest Main Category:"),
                                                   alignment=Qt.AlignLeft)
        self.interest_main_category_sel = QComboBox()
        self.interest_main_category_sel_list = ['any', "custom"]
        for p in self.interest_main_category_sel_list:
            self.interest_main_category_sel.addItem(QApplication.translate("QComboBox", p))
        self.interest_main_category_sel.currentTextChanged.connect(self.interestMainCategorySel_changed)

        self.interest_sub_category1_label = QLabel(QApplication.translate("QLabel", "Interest Sub Category1:"),
                                                   alignment=Qt.AlignLeft)
        self.interest_sub_category1_sel = QComboBox()
        self.interest_main_category1_sel_list = ['any', "custom"]
        for p in self.interest_main_category1_sel_list:
            self.interest_sub_category1_sel.addItem(QApplication.translate("QComboBox", p))
        self.interest_sub_category1_sel.currentTextChanged.connect(self.interestSubCategory1Sel_changed)

        self.interest_sub_category2_label = QLabel(QApplication.translate("QLabel", "Interest Sub Category2:"),
                                                   alignment=Qt.AlignLeft)
        self.interest_sub_category2_sel = QComboBox()
        self.interest_main_category2_sel_list = ['any', "custom"]
        for p in self.interest_main_category2_sel_list:
            self.interest_sub_category2_sel.addItem(QApplication.translate("QComboBox", p))
        self.interest_sub_category2_sel.currentTextChanged.connect(self.interestSubCategory2Sel_changed)

        self.interest_sub_category3_label = QLabel(QApplication.translate("QLabel", "Interest Sub Category3:"),
                                                   alignment=Qt.AlignLeft)
        self.interest_sub_category3_sel = QComboBox()
        self.interest_main_category3_sel_list = ['any', "custom"]
        for p in self.interest_main_category3_sel_list:
            self.interest_sub_category3_sel.addItem(QApplication.translate("QComboBox", p))
        self.interest_sub_category3_sel.currentTextChanged.connect(self.interestSubCategory3Sel_changed)

        # self.interest_sub_category4_label = QLabel(QApplication.translate("QLabel", "Interest Sub Category4:"), alignment=Qt.AlignLeft)
        # self.interest_sub_category4_sel = QComboBox()
        # self.interest_sub_category4_sel.addItem(QApplication.translate("QComboBox", "any"))
        # self.interest_sub_category4_sel.addItem(QApplication.translate("QComboBox", "custom"))
        # self.interest_sub_category4_sel.currentTextChanged.connect(self.interestSubCategory4Sel_changed)
        #
        #
        # self.interest_sub_category5_label = QLabel(QApplication.translate("QLabel", "Interest Sub Category5:"), alignment=Qt.AlignLeft)
        # self.interest_sub_category5_sel = QComboBox()
        # self.interest_sub_category5_sel.addItem(QApplication.translate("QComboBox", "any"))
        # self.interest_sub_category5_sel.addItem(QApplication.translate("QComboBox", "custom"))
        # self.interest_sub_category5_sel.currentTextChanged.connect(self.interestSubCategory5Sel_changed)

        QApplication.translate("QLabel", "Interest Custom Main Sub Category1:")
        self.interest_custom_platform_label = QLabel(QApplication.translate("QLabel", "Interest Custom platform:"),
                                                     alignment=Qt.AlignLeft)
        self.interest_custom_platform_edit = QLineEdit()
        self.interest_custom_main_category_label = QLabel(
            QApplication.translate("QLabel", "Interest Custom Main Category:"), alignment=Qt.AlignLeft)
        self.interest_custom_main_category_edit = QLineEdit()
        self.interest_custom_sub_category1_label = QLabel(
            QApplication.translate("QLabel", "Interest Custom Main Sub Category1:"), alignment=Qt.AlignLeft)
        self.interest_custom_sub_category1_edit = QLineEdit()
        self.interest_custom_sub_category2_label = QLabel(
            QApplication.translate("QLabel", "Interest Custom Main Sub Category2:"), alignment=Qt.AlignLeft)
        self.interest_custom_sub_category2_edit = QLineEdit()
        self.interest_custom_sub_category3_label = QLabel(
            QApplication.translate("QLabel", "Interest Custom Main Sub Category3:"), alignment=Qt.AlignLeft)
        self.interest_custom_sub_category3_edit = QLineEdit()
        # self.interest_custom_sub_category4_label = QLabel(QApplication.translate("QLabel", "Interest Custom Main Sub Category4:"), alignment=Qt.AlignLeft)
        # self.interest_custom_sub_category4_edit = QLineEdit()
        # self.interest_custom_sub_category5_label = QLabel(QApplication.translate("QLabel", "Interest Custom Main Sub Category5:"), alignment=Qt.AlignLeft)
        # self.interest_custom_sub_category5_edit = QLineEdit()

        self.role_platform_label = QLabel(QApplication.translate("QLabel", "<b style='color:red;'>Platform:</b>"),
                                          alignment=Qt.AlignLeft)
        self.role_platform_edit = QLineEdit()
        self.role_platform_sel = QComboBox()

        for p in self.static_resource.SITES:
            self.role_platform_sel.addItem(QApplication.translate("QComboBox", p))

        self.role_platform_sel.currentTextChanged.connect(self.rolePlatformSel_changed)
        self.role_custom_platform_label = QLabel(QApplication.translate("QLabel", "Custom Platform:"),
                                                 alignment=Qt.AlignLeft)
        self.role_custom_platform_edit = QLineEdit()
        self.role_level_label = QLabel(QApplication.translate("QLabel", "Level:"), alignment=Qt.AlignLeft)
        self.role_level_edit = QLineEdit()
        self.role_level_sel = QComboBox()
        self.role_level_sel_list = ["Green", "Experienced", "Expert", "Master", "Champ"]
        for role_level_sel in self.role_level_sel_list:
            self.role_level_sel.addItem(QApplication.translate("QComboBox", role_level_sel))
        QApplication.translate("QComboBox", "Champ")
        self.role_level_sel.currentTextChanged.connect(self.roleLevelSel_changed)
        self.role_name_label = QLabel(QApplication.translate("QLabel", "<b style='color:red;'>Role:</b>"),
                                      alignment=Qt.AlignLeft)
        self.role_name_edit = QLineEdit()
        self.role_name_sel = QComboBox()
        self.role_name_sel_list = ["Buyer", "Seller", "Manager", "HR", "Legal", "Finance", "Operator"]
        for role_name_sel in self.role_name_sel_list:
            self.role_name_sel.addItem(QApplication.translate("QComboBox", role_name_sel))
        self.role_name_sel.currentTextChanged.connect(self.roleNameSel_changed)

        self.pubpflLine1Layout = QHBoxLayout(self)
        self.pubpflLine1Layout.addWidget(self.tag_label)
        self.pubpflLine1Layout.addWidget(self.tag_edit)
        self.pubpflWidget_layout.addLayout(self.pubpflLine1Layout)

        self.pubpflLine2Layout = QHBoxLayout(self)
        self.pubpflLine2Layout.addWidget(self.icon_label)
        self.pubpflLine2Layout.addWidget(self.icon_path_edit)
        self.pubpflLine2Layout.addWidget(self.icon_fs_button)
        self.pubpflWidget_layout.addLayout(self.pubpflLine2Layout)

        self.pubpflLine3Layout = QHBoxLayout(self)
        self.pubpflLine3Layout.addWidget(self.pfn_label)
        self.pubpflLine3Layout.addWidget(self.pfn_edit)
        self.pubpflLine3Layout.addWidget(self.pln_label)
        self.pubpflLine3Layout.addWidget(self.pln_edit)
        self.pubpflWidget_layout.addLayout(self.pubpflLine3Layout)

        self.pubpflLine4Layout = QHBoxLayout(self)
        self.pubpflLine4Layout.addWidget(self.pnn_label)
        self.pubpflLine4Layout.addWidget(self.pnn_edit)
        self.pubpflWidget_layout.addLayout(self.pubpflLine4Layout)

        self.pubpflLine5Layout = QHBoxLayout(self)
        self.pubpflLine5Layout.addWidget(self.loccity_label)
        self.pubpflLine5Layout.addWidget(self.loccity_edit)
        self.pubpflLine5Layout.addWidget(self.locstate_label)
        self.pubpflLine5Layout.addWidget(self.locstate_edit)
        self.pubpflWidget_layout.addLayout(self.pubpflLine5Layout)

        self.pubpflLine5ALayout = QHBoxLayout(self)
        self.pubpflLine5ALayout.addWidget(self.bd_label)
        self.pubpflLine5ALayout.addWidget(self.bd_edit)
        self.pubpflWidget_layout.addLayout(self.pubpflLine5ALayout)

        self.pubpflLine6Layout = QHBoxLayout(self)
        self.pubpflLine6Layout.addWidget(self.age_label)
        self.pubpflLine6Layout.addWidget(self.age_edit)
        self.pubpflWidget_layout.addLayout(self.pubpflLine6Layout)

        self.pubpflLine6ALayout = QHBoxLayout(self)
        self.pubpflLine6ALayout.addWidget(self.vehicle_label)
        self.pubpflLine6ALayout.addWidget(self.vehicle_combo_box)
        self.pubpflWidget_layout.addLayout(self.pubpflLine6ALayout)

        self.pubpflLine7Layout = QHBoxLayout(self)
        self.pubpflLine7Layout.addWidget(self.mf_label)
        self.pubpflLine7Layout.addWidget(self.m_rb)
        self.pubpflLine7Layout.addWidget(self.f_rb)
        self.pubpflLine7Layout.addWidget(self.gna_rb)
        self.pubpflWidget_layout.addLayout(self.pubpflLine7Layout)

        self.pubpflLine7AALayout = QHBoxLayout(self)
        self.pubpflLine7AALayout.addWidget(self.interest_area_label)
        self.pubpflWidget_layout.addLayout(self.pubpflLine7AALayout)

        self.pubpflLine7ALayout = QHBoxLayout(self)
        self.pubpflLine7ALayout.addWidget(self.interest_platform_label)
        self.pubpflLine7ALayout.addWidget(self.interest_platform_sel)
        self.pubpflLine7ALayout.addWidget(self.interest_main_category_label)
        self.pubpflLine7ALayout.addWidget(self.interest_main_category_sel)
        self.pubpflLine7ALayout.addWidget(self.interest_sub_category1_label)
        self.pubpflLine7ALayout.addWidget(self.interest_sub_category1_sel)
        self.pubpflWidget_layout.addLayout(self.pubpflLine7ALayout)

        self.pubpflLine7BLayout = QHBoxLayout(self)
        self.pubpflLine7BLayout.addWidget(self.interest_sub_category2_label)
        self.pubpflLine7BLayout.addWidget(self.interest_sub_category2_sel)
        self.pubpflLine7BLayout.addWidget(self.interest_sub_category3_label)
        self.pubpflLine7BLayout.addWidget(self.interest_sub_category3_sel)
        # self.pubpflLine7BLayout.addWidget(self.interest_sub_category4_label)
        # self.pubpflLine7BLayout.addWidget(self.interest_sub_category4_sel)
        # self.pubpflLine7BLayout.addWidget(self.interest_sub_category5_label)
        # self.pubpflLine7BLayout.addWidget(self.interest_sub_category5_sel)
        self.pubpflWidget_layout.addLayout(self.pubpflLine7BLayout)

        self.pubpflLine7DLayout = QHBoxLayout(self)
        self.pubpflLine7DLayout.addWidget(self.interest_custom_platform_label)
        self.pubpflLine7DLayout.addWidget(self.interest_custom_platform_edit)
        self.pubpflLine7DLayout.addWidget(self.interest_custom_main_category_label)
        self.pubpflLine7DLayout.addWidget(self.interest_custom_main_category_edit)
        self.pubpflLine7DLayout.addWidget(self.interest_custom_sub_category1_label)
        self.pubpflLine7DLayout.addWidget(self.interest_custom_sub_category1_edit)
        self.pubpflWidget_layout.addLayout(self.pubpflLine7DLayout)

        self.pubpflLine7ELayout = QHBoxLayout(self)
        self.pubpflLine7ELayout.addWidget(self.interest_custom_sub_category2_label)
        self.pubpflLine7ELayout.addWidget(self.interest_custom_sub_category2_edit)
        self.pubpflLine7ELayout.addWidget(self.interest_custom_sub_category3_label)
        self.pubpflLine7ELayout.addWidget(self.interest_custom_sub_category3_edit)
        # self.pubpflLine7ELayout.addWidget(self.interest_custom_sub_category4_label)
        # self.pubpflLine7ELayout.addWidget(self.interest_custom_sub_category4_edit)
        # self.pubpflLine7ELayout.addWidget(self.interest_custom_sub_category5_label)
        # self.pubpflLine7ELayout.addWidget(self.interest_custom_sub_category5_edit)
        self.pubpflWidget_layout.addLayout(self.pubpflLine7ELayout)

        self.hide_interest_custom_platform()
        self.hide_interest_custom_main_category()
        self.hide_interest_custom_sub_category1()
        self.hide_interest_custom_sub_category2()
        self.hide_interest_custom_sub_category3()
        # self.hide_interest_custom_sub_category4()
        # self.hide_interest_custom_sub_category5()
        self.pubpflWidget_layout.addWidget(self.interest_save_button)
        self.pubpflWidget_layout.addWidget(self.interestScrollLabel)
        self.pubpflWidget_layout.addWidget(self.interestTableView)

        self.pubpflLine8Layout = QHBoxLayout(self)
        self.pubpflLine8Layout.addWidget(self.role_platform_label)
        self.pubpflLine8Layout.addWidget(self.role_platform_sel)
        self.pubpflLine8Layout.addWidget(self.role_level_label)
        self.pubpflLine8Layout.addWidget(self.role_level_sel)
        self.pubpflLine8Layout.addWidget(self.role_name_label)
        self.pubpflLine8Layout.addWidget(self.role_name_sel)
        self.pubpflLine8Layout.addWidget(self.role_save_button)
        self.pubpflWidget_layout.addLayout(self.pubpflLine8Layout)

        self.pubpflLine9Layout = QHBoxLayout(self)
        self.pubpflLine9Layout.addWidget(self.role_custom_platform_label)
        self.pubpflLine9Layout.addWidget(self.role_custom_platform_edit)

        self.pubpflWidget_layout.addLayout(self.pubpflLine9Layout)
        self.hide_role_custom_platform()
        self.pubpflWidget_layout.addWidget(self.roleScrollLabel)
        self.pubpflWidget_layout.addWidget(self.roleTableView)

        # self.pubpflLine8Layout = QHBoxLayout(self)
        # self.pubpflLine8Layout.addWidget(self.pnn_label)
        # self.pubpflLine8Layout.addWidget(self.pnn_edit)
        # self.pubpflWidget.layout.addLayout(self.pubpflLine8Layout)

        self.pubpflWidget.setLayout(self.pubpflWidget_layout)

        self.fn_label = QLabel(QApplication.translate("QLabel", "<b style='color:red;'>First Name:</b>"),
                               alignment=Qt.AlignLeft)
        self.fn_edit = QLineEdit()

        self.fn_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input First Name here"))
        self.ln_label = QLabel(QApplication.translate("QLabel", "<b style='color:red;'>Last Name:</b>"),
                               alignment=Qt.AlignLeft)
        self.ln_edit = QLineEdit()
        self.ln_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input Last Name here"))

        self.addr_label = QLabel(QApplication.translate("QLabel", "<b style='color:red;'>Address:</b>"), alignment=Qt.AlignLeft)
        self.addr_label.setFixedHeight(30)

        self.shipaddr_label = QLabel(QApplication.translate("QLabel", "Shipping Address:"), alignment=Qt.AlignLeft)
        self.shipaddr_label.setFixedHeight(30)

        self.addr_l1_label = QLabel(QApplication.translate("QLabel", "Address Line1:"), alignment=Qt.AlignLeft)
        self.addr_l1_edit = QLineEdit()

        self.addr_l2_label = QLabel(QApplication.translate("QLabel", "Address Line2:"), alignment=Qt.AlignLeft)
        self.addr_l2_edit = QLineEdit()

        self.addr_city_label = QLabel(QApplication.translate("QLabel", "City:"), alignment=Qt.AlignLeft)
        self.addr_city_edit = QLineEdit()
        self.addr_state_label = QLabel(QApplication.translate("QLabel", "State:"), alignment=Qt.AlignLeft)
        self.addr_state_edit = QLineEdit()
        self.addr_zip_label = QLabel(QApplication.translate("QLabel", "ZIP:"), alignment=Qt.AlignLeft)
        self.addr_zip_edit = QLineEdit()

        self.shipaddr_same_label = QLabel(
            QApplication.translate("QLabel", "<b style='color:red;'>Shipping Address Same As Address?</b>"),
            alignment=Qt.AlignLeft)
        self.shipaddr_same_checkbox = QCheckBox()
        self.shipaddr_same_checkbox.setCheckState(Qt.CheckState.Unchecked)
        self.shipaddr_same_checkbox.stateChanged.connect(self.shipaddr_same_checkbox_toggled)

        self.shipaddr_l1_label = QLabel(QApplication.translate("QLabel", "Shipping Address Line1:"),
                                        alignment=Qt.AlignLeft)
        self.shipaddr_l1_edit = QLineEdit()

        self.shipaddr_l2_label = QLabel(QApplication.translate("QLabel", "Shipping Address Line2:"),
                                        alignment=Qt.AlignLeft)
        self.shipaddr_l2_edit = QLineEdit()

        self.shipaddr_city_label = QLabel(QApplication.translate("QLabel", "City:"), alignment=Qt.AlignLeft)
        self.shipaddr_city_edit = QLineEdit()
        self.shipaddr_state_label = QLabel(QApplication.translate("QLabel", "State:"), alignment=Qt.AlignLeft)
        self.shipaddr_state_edit = QLineEdit()
        self.shipaddr_zip_label = QLabel(QApplication.translate("QLabel", "Zip:"), alignment=Qt.AlignLeft)
        self.shipaddr_zip_edit = QLineEdit()

        self.phone_label = QLabel(QApplication.translate("QLabel", "Contact Phone:"), alignment=Qt.AlignLeft)
        self.phone_edit = QLineEdit()
        self.phone_edit.setPlaceholderText(QApplication.translate("QLineEdit", "(optional) contact phone number here"))
        self.em_label = QLabel(QApplication.translate("QLabel", "<b style='color:red;'>User Email:</b>"),
                               alignment=Qt.AlignLeft)
        self.em_edit = QLineEdit()
        self.em_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input email here"))
        self.empw_label = QLabel(QApplication.translate("QLabel", "<b style='color:red;'>Email Password:</b>"),
                                 alignment=Qt.AlignLeft)
        self.empw_edit = QLineEdit()
        self.empw_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input Email Password here"))
        self.backem_label = QLabel(QApplication.translate("QLabel", "<b style='color:red;'>Back Up Email:</b>"),
                                   alignment=Qt.AlignLeft)
        self.backem_edit = QLineEdit()
        self.backem_edit.setPlaceholderText(QApplication.translate("QLineEdit", "(optional) back up email here"))
        self.acctpw_label = QLabel(
            QApplication.translate("QLabel", "<b style='color:red;'>E-Business Account Password:</b>"),
            alignment=Qt.AlignLeft)
        self.acctpw_edit = QLineEdit("")
        self.acctpw_edit.setPlaceholderText(
            QApplication.translate("QLineEdit", "(optional) E-Business Account Password here"))
        self.backem_site_label = QLabel(
            QApplication.translate("QLabel", "<b style='color:red;'>Backup Email Site:</b>"), alignment=Qt.AlignLeft)
        self.backem_site_edit = QLineEdit("")
        self.backem_site_edit.setPlaceholderText(QApplication.translate("QLineEdit", "website for access backup email"))

        self.prvpflLine0Layout = QHBoxLayout(self)
        self.prvpflLine0Layout.addWidget(self.private_attribute_note_label)
        self.prvpflWidget_layout.addLayout(self.prvpflLine0Layout)

        self.prvpflLine1Layout = QHBoxLayout(self)
        self.prvpflLine1Layout.addWidget(self.fn_label)
        self.prvpflLine1Layout.addWidget(self.fn_edit)
        self.prvpflLine1Layout.addWidget(self.ln_label)
        self.prvpflLine1Layout.addWidget(self.ln_edit)
        self.prvpflWidget_layout.addLayout(self.prvpflLine1Layout)

        self.prvpflLine1A1Layout = QHBoxLayout(self)
        self.prvpflLine1A1Layout.addWidget(self.addr_label)
        self.prvpflWidget_layout.addLayout(self.prvpflLine1A1Layout)

        self.prvpflLine1BLayout = QHBoxLayout(self)
        self.prvpflLine1BLayout.addWidget(self.addr_l1_label)
        self.prvpflLine1BLayout.addWidget(self.addr_l1_edit)
        self.prvpflWidget_layout.addLayout(self.prvpflLine1BLayout)

        self.prvpflLine1CLayout = QHBoxLayout(self)
        self.prvpflLine1CLayout.addWidget(self.addr_l2_label)
        self.prvpflLine1CLayout.addWidget(self.addr_l2_edit)
        self.prvpflWidget_layout.addLayout(self.prvpflLine1CLayout)

        self.prvpflLine1DLayout = QHBoxLayout(self)
        self.prvpflLine1DLayout.addWidget(self.addr_city_label)
        self.prvpflLine1DLayout.addWidget(self.addr_city_edit)
        self.prvpflLine1DLayout.addWidget(self.addr_state_label)
        self.prvpflLine1DLayout.addWidget(self.addr_state_edit)
        self.prvpflLine1DLayout.addWidget(self.addr_zip_label)
        self.prvpflLine1DLayout.addWidget(self.addr_zip_edit)
        self.prvpflWidget_layout.addLayout(self.prvpflLine1DLayout)

        self.prvpflLine1E1Layout = QHBoxLayout(self)
        self.prvpflLine1E1Layout.addWidget(self.shipaddr_label)
        self.prvpflWidget_layout.addLayout(self.prvpflLine1E1Layout)

        self.prvpflLine1ELayout = QHBoxLayout(self)
        self.prvpflLine1ELayout.addWidget(self.shipaddr_same_label)
        self.prvpflLine1ELayout.addWidget(self.shipaddr_same_checkbox)
        self.prvpflWidget_layout.addLayout(self.prvpflLine1ELayout)

        self.prvpflLine1FLayout = QHBoxLayout(self)
        self.prvpflLine1FLayout.addWidget(self.shipaddr_l1_label)
        self.prvpflLine1FLayout.addWidget(self.shipaddr_l1_edit)
        self.prvpflWidget_layout.addLayout(self.prvpflLine1FLayout)

        self.prvpflLine1GLayout = QHBoxLayout(self)
        self.prvpflLine1GLayout.addWidget(self.shipaddr_l2_label)
        self.prvpflLine1GLayout.addWidget(self.shipaddr_l2_edit)
        self.prvpflWidget_layout.addLayout(self.prvpflLine1GLayout)

        self.prvpflLine1HLayout = QHBoxLayout(self)
        self.prvpflLine1HLayout.addWidget(self.shipaddr_city_label)
        self.prvpflLine1HLayout.addWidget(self.shipaddr_city_edit)
        self.prvpflLine1HLayout.addWidget(self.shipaddr_state_label)
        self.prvpflLine1HLayout.addWidget(self.shipaddr_state_edit)
        self.prvpflLine1HLayout.addWidget(self.shipaddr_zip_label)
        self.prvpflLine1HLayout.addWidget(self.shipaddr_zip_edit)
        self.prvpflWidget_layout.addLayout(self.prvpflLine1HLayout)

        self.prvpflLine2Layout = QHBoxLayout(self)
        self.prvpflLine2Layout.addWidget(self.phone_label)
        self.prvpflLine2Layout.addWidget(self.phone_edit)
        self.prvpflWidget_layout.addLayout(self.prvpflLine2Layout)

        self.prvpflLine3Layout = QHBoxLayout(self)
        self.prvpflLine3Layout.addWidget(self.em_label)
        self.prvpflLine3Layout.addWidget(self.em_edit)
        self.prvpflLine3Layout.addWidget(self.empw_label)
        self.prvpflLine3Layout.addWidget(self.empw_edit)
        self.prvpflWidget_layout.addLayout(self.prvpflLine3Layout)

        self.prvpflLine4Layout = QHBoxLayout(self)
        self.prvpflLine4Layout.addWidget(self.backem_label)
        self.prvpflLine4Layout.addWidget(self.backem_edit)

        self.prvpflLine4Layout.addWidget(self.acctpw_label)
        self.prvpflLine4Layout.addWidget(self.acctpw_edit)
        self.prvpflWidget_layout.addLayout(self.prvpflLine4Layout)

        self.prvpflLine5Layout = QHBoxLayout(self)
        self.prvpflLine5Layout.addWidget(self.backem_site_label)
        self.prvpflLine5Layout.addWidget(self.backem_site_edit)
        self.prvpflWidget_layout.addLayout(self.prvpflLine5Layout)

        self.prvpflWidget.setLayout(self.prvpflWidget_layout)
        QApplication.translate("QLabel", "App Name:")
        self.browser_label = QLabel(QApplication.translate("QLabel", "App Name:"), alignment=Qt.AlignLeft)
        self.browser_sel = QComboBox()
        for app in self.static_resource.APPS:
            self.browser_sel.addItem(QApplication.translate("QComboBox", app))

        self.os_label = QLabel(QApplication.translate("QLabel", "<b style='color:red;'>OS Type:</b>"),
                               alignment=Qt.AlignLeft)
        self.os_sel = QComboBox()
        for cos in self.static_resource.PLATFORMS:
            self.os_sel.addItem(QApplication.translate("QComboBox", cos))

        self.machine_label = QLabel(QApplication.translate("QLabel", "Machine Type:"), alignment=Qt.AlignLeft)
        self.machine_sel = QComboBox()
        self.machine_sel.addItem(QApplication.translate("QComboBox", "Mac"))
        self.machine_sel.addItem(QApplication.translate("QComboBox", "Intel"))

        self.setngsLine1Layout = QHBoxLayout(self)
        self.setngsLine1Layout.addWidget(self.machine_label)
        self.setngsLine1Layout.addWidget(self.machine_sel)
        self.setngsWidget_layout.addLayout(self.setngsLine1Layout)

        self.setngsLine2Layout = QHBoxLayout(self)
        self.setngsLine2Layout.addWidget(self.os_label)
        self.setngsLine2Layout.addWidget(self.os_sel)
        self.setngsWidget_layout.addLayout(self.setngsLine2Layout)

        self.setngsLine3Layout = QHBoxLayout(self)
        self.setngsLine3Layout.addWidget(self.browser_label)
        self.setngsLine3Layout.addWidget(self.browser_sel)
        self.setngsWidget_layout.addLayout(self.setngsLine3Layout)

        self.setngsWidget.setLayout(self.setngsWidget_layout)

        self.state_label = QLabel(QApplication.translate("QLabel", "<b style='color:red;'>Status:</b>"),
                                  alignment=Qt.AlignLeft)
        self.state_select = QComboBox()
        for botstat in self.main_win.bot_states:
            self.state_select.addItem(QApplication.translate("QComboBox", botstat))

        self.state_select.setCurrentIndex(0)    # make active as default, this will corrected by the actual data.
        self.state_select.currentTextChanged.connect(self.state_select_changed)


        self.statLine1Layout = QHBoxLayout(self)
        self.statLine1Layout.addWidget(self.state_label)
        self.statLine1Layout.addWidget(self.state_select)
        self.statWidget_layout.addLayout(self.statLine1Layout)

        self.statWidget.setLayout(self.statWidget_layout)

        self.tabs.addTab(self.pubpflWidget, QApplication.translate("QTabWidget", "Pub Profile"))
        self.tabs.addTab(self.prvpflWidget, QApplication.translate("QTabWidget", "Private Profile"))
        self.tabs.addTab(self.setngsWidget, QApplication.translate("QTabWidget", "Settings"))
        self.tabs.addTab(self.statWidget, QApplication.translate("QTabWidget", "Status"))
        self.layout.addWidget(self.tabs)
        self.layout.addLayout(self.bLayout)

        # self.layout.addWidget(self.text)
        # self.layout.addRow(self.browser_path_label, self.browser_path_line_edit);
        # self.layout.addRow(self.date_time_label, self.date_time_start)
        # self.layout.addRow(self.task_settings_button)
        # self.layout.addRow(self.cancel_button, self.save_button)

        self.interest_save_button.clicked.connect(self.addInterest)
        self.role_save_button.clicked.connect(self.saveRole)
        self.save_button.clicked.connect(self.saveBot)
        self.cancel_button.clicked.connect(self.close)

        self.mainWidget.setLayout(self.layout)
        self.setCentralWidget(self.mainWidget)
        self.setWindowTitle("Bot Editor")

    def hide_role_custom_platform(self):
        self.role_custom_platform_label.setVisible(False)
        self.role_custom_platform_edit.setVisible(False)

    def show_role_custom_platform(self):
        self.role_custom_platform_label.setVisible(True)
        self.role_custom_platform_edit.setVisible(True)

    def hide_interest_custom_platform(self):
        self.interest_custom_platform_label.setVisible(False)
        self.interest_custom_platform_edit.setVisible(False)

    def show_interest_custom_platform(self):
        self.interest_custom_platform_label.setVisible(True)
        self.interest_custom_platform_edit.setVisible(True)

    def hide_interest_custom_main_category(self):
        self.interest_custom_main_category_label.setVisible(False)
        self.interest_custom_main_category_edit.setVisible(False)

    def show_interest_custom_main_category(self):
        self.interest_custom_main_category_label.setVisible(True)
        self.interest_custom_main_category_edit.setVisible(True)

    def hide_interest_custom_sub_category1(self):
        self.interest_custom_sub_category1_label.setVisible(False)
        self.interest_custom_sub_category1_edit.setVisible(False)

    def show_interest_custom_sub_category1(self):
        self.interest_custom_sub_category1_label.setVisible(True)
        self.interest_custom_sub_category1_edit.setVisible(True)

    def hide_interest_custom_sub_category2(self):
        self.interest_custom_sub_category2_label.setVisible(False)
        self.interest_custom_sub_category2_edit.setVisible(False)

    def show_interest_custom_sub_category2(self):
        self.interest_custom_sub_category2_label.setVisible(True)
        self.interest_custom_sub_category2_edit.setVisible(True)

    def hide_interest_custom_sub_category3(self):
        self.interest_custom_sub_category3_label.setVisible(False)
        self.interest_custom_sub_category3_edit.setVisible(False)

    def show_interest_custom_sub_category3(self):
        self.interest_custom_sub_category3_label.setVisible(True)
        self.interest_custom_sub_category3_edit.setVisible(True)

    # def hide_interest_custom_sub_category4(self):
    #     self.interest_custom_sub_category4_label.setVisible(False)
    #     self.interest_custom_sub_category4_edit.setVisible(False)
    #
    # def show_interest_custom_sub_category4(self):
    #     self.interest_custom_sub_category4_label.setVisible(True)
    #     self.interest_custom_sub_category4_edit.setVisible(True)
    #
    # def hide_interest_custom_sub_category5(self):
    #     self.interest_custom_sub_category5_label.setVisible(False)
    #     self.interest_custom_sub_category5_edit.setVisible(False)
    #
    # def show_interest_custom_sub_category5(self):
    #     self.interest_custom_sub_category5_label.setVisible(True)
    #     self.interest_custom_sub_category5_edit.setVisible(True)

    def state_select_changed(self):
        self.botStatus = self.state_select.currentText()

    def saveRole(self):
        if self.role_platform_sel.currentText() == QApplication.translate("QComboBox", "Custom"):
            self.selected_role_platform = self.role_custom_platform_edit.text()
        rowCount = self.roleTableModel.rowCount()
        self.roleTableModel.setItem(rowCount, 0, QStandardItem(self.selected_role_platform))
        self.roleTableModel.setItem(rowCount, 1, QStandardItem(self.selected_role_level))
        self.roleTableModel.setItem(rowCount, 2, QStandardItem(self.selected_role_role))
        self.role_custom_platform_edit.clear()

    def addInterest(self):
        if self.interest_platform_sel.currentText() == QApplication.translate("QComboBox", "Custom"):
            self.selected_interest_platform = self.interest_custom_platform_edit.text()

        if self.interest_main_category_sel.currentText() == QApplication.translate("QComboBox", "Custom"):
            self.selected_interest_main_category = self.interest_custom_main_category_edit.text()

        if self.interest_sub_category1_sel.currentText() == QApplication.translate("QComboBox", "Custom"):
            self.selected_interest_sub_category1 = self.interest_custom_sub_category1_edit.text()

        if self.interest_sub_category2_sel.currentText() == QApplication.translate("QComboBox", "Custom"):
            self.selected_interest_sub_category2 = self.interest_custom_sub_category2_edit.text()

        if self.interest_sub_category3_sel.currentText() == QApplication.translate("QComboBox", "Custom"):
            self.selected_interest_sub_category3 = self.interest_custom_sub_category3_edit.text()

        # if self.interest_sub_category4_sel.currentText() == QApplication.translate("QComboBox", "Custom"):
        #     self.selected_interest_sub_category4 = self.interest_custom_sub_category4_edit.text()
        #
        # if self.interest_sub_category5_sel.currentText() == QApplication.translate("QComboBox", "Custom"):
        #     self.selected_interest_sub_category5 = self.interest_custom_sub_category5_edit.text()
        rowCount = self.interestTableModel.rowCount()
        self.interestTableModel.setItem(rowCount, 0, QStandardItem(self.selected_interest_platform))
        self.interestTableModel.setItem(rowCount, 1, QStandardItem(self.selected_interest_main_category))
        self.interestTableModel.setItem(rowCount, 2, QStandardItem(self.selected_interest_sub_category1))
        self.interestTableModel.setItem(rowCount, 3, QStandardItem(self.selected_interest_sub_category2))
        self.interestTableModel.setItem(rowCount, 4, QStandardItem(self.selected_interest_sub_category3))

    # fill GUI from data.
    def setBot(self, bot):
        self.newBot = bot
        self.tabs.setCurrentIndex(0)
        # now populate the GUI to reflect info in this bot.
        self.acctpw_edit.setText(bot.getAcctPw())
        self.age_edit.setText(str(bot.getAge()))
        self.bd_edit.setText(bot.getPubBirthday())
        self.backem_edit.setText(bot.getBackEm())
        if bot.getLocation() == "":
            self.loccity_edit.setText("")
            self.locstate_edit.setText("")
        else:
            self.loccity_edit.setText(bot.getLocation().split(",")[0])
            self.locstate_edit.setText(bot.getLocation().split(",")[1])
        self.em_edit.setText(bot.getEmail())
        self.empw_edit.setText(bot.getEmPW())
        self.backem_edit.setText(bot.getBackEm())
        self.fn_edit.setText(bot.getFn())
        self.ln_edit.setText(bot.getLn())
        self.pln_edit.setText(bot.getPseudoLastName())
        self.pfn_edit.setText(bot.getPseudoFirstName())
        self.backem_site_edit.setText(bot.getBackEmSite())
        self.pnn_edit.setText(bot.getNickName())
        self.phone_edit.setText(bot.getPhone())
        self.tag_edit.setReadOnly(False)
        self.tag_edit.setText(str(bot.getBid()))
        self.tag_edit.setReadOnly(True)
        if bot.getGender() == "Male":
            self.m_rb.setChecked(True)
        elif bot.getGender() == "Female":
            self.f_rb.setChecked(True)
        else:
            self.gna_rb.setChecked(True)
        self.os_sel.setCurrentText(bot.getOS())
        self.browser_sel.setCurrentText(bot.getBrowser())
        self.machine_sel.setCurrentText(bot.getMachine())
        self.addr_l1_edit.setText(bot.getAddrStreet1())
        self.addr_l2_edit.setText(bot.getAddrStreet2())
        self.addr_city_edit.setText(bot.getAddrCity())
        self.addr_state_edit.setText(bot.getAddrState())
        self.addr_zip_edit.setText(bot.getAddrZip())
        if bot.getAddrShippingAddrSame():
            self.shipaddr_same_checkbox.setChecked(True)
            self.shipaddr_l1_edit.setText(self.addr_l1_edit.text())
            self.shipaddr_l2_edit.setText(self.addr_l2_edit.text())
            self.shipaddr_city_edit.setText(self.addr_city_edit.text())
            self.shipaddr_state_edit.setText(self.addr_state_edit.text())
            self.shipaddr_zip_edit.setText(self.addr_zip_edit.text())
        else:
            self.shipaddr_same_checkbox.setChecked(False)

            self.shipaddr_l1_edit.setText(bot.getShippingAddrStreet1())
            self.shipaddr_l2_edit.setText(bot.getShippingAddrStreet2())
            self.shipaddr_city_edit.setText(bot.getShippingAddrCity())
            self.shipaddr_state_edit.setText(bot.getShippingAddrState())
            self.shipaddr_zip_edit.setText(bot.getShippingAddrZip())

        if bot.getVehicle() == "NA" or bot.getVehicle() == "" or bot.getVehicle() is None:
            self.vehicle_combo_box.setCurrentIndex(-1)
        else:
            index = self.vehicle_list.index(bot.getVehicle())
            self.vehicle_combo_box.setCurrentIndex(index)
        self.load_role(bot)
        self.load_interests(bot)
        state_index = next((i for i, bs in enumerate(self.main_win.bot_states) if self.newBot.getStatus() == bs), -1)
        if state_index >= 0:
            self.state_select.setCurrentIndex(state_index)
        else:
            self.state_select.setCurrentIndex(0)              # active is the default state.

    def load_role(self, bot):
        self.roleTableModel.clear()
        headers = ["Platform", "Level", "Role"]
        for col, header in enumerate(headers):
            item = QStandardItem(header)
            # 设置表头项不可编辑（可选）
            item.setEditable(False)
            # 设置对齐方式（可选）
            item.setTextAlignment(Qt.AlignCenter)
            self.roleTableModel.setHorizontalHeaderItem(col, item)
        all_roles = bot.getLevels()
        if all_roles != "":
            roles = all_roles.split(",")
            for i, r in enumerate(roles):
                role_parts = r.split(":")
                for j, l in enumerate(role_parts):
                    item = QStandardItem(l)
                    self.roleTableModel.setItem(i, j, item)
        platformSelect = ComboBoxDelegate(self.roleTableView, self.static_resource.SITES)
        self.roleTableView.setItemDelegateForColumn(0, platformSelect)
        roleLevelSelect = ComboBoxDelegate(self.roleTableView, self.role_level_sel_list)
        self.roleTableView.setItemDelegateForColumn(1, roleLevelSelect)
        roleNameSelect = ComboBoxDelegate(self.roleTableView, self.role_name_sel_list)
        self.roleTableView.setItemDelegateForColumn(2, roleNameSelect)

    def load_interests(self, bot):
        self.interestTableModel.clear()
        headers = ["Platform", "Main Category", "Sub Category 1", "Sub Category 2", "Sub Category 3"]
        for col, header in enumerate(headers):
            item = QStandardItem(header)
            # 设置表头项不可编辑（可选）
            item.setEditable(False)
            # 设置对齐方式（可选）
            item.setTextAlignment(Qt.AlignCenter)
            self.interestTableModel.setHorizontalHeaderItem(col, item)
        all_ints = bot.getInterests()
        if all_ints != "":
            ints = all_ints.split(",")
            for i, r in enumerate(ints):
                int_parts = r.split("|")
                for j, l in enumerate(int_parts):
                    item = QStandardItem(l)
                    self.interestTableModel.setItem(i, j, item)
        platformSelect = ComboBoxDelegate(self.interestTableView, self.interest_platform_sel_list)
        self.interestTableView.setItemDelegateForColumn(0, platformSelect)
        mainCategorySelect = ComboBoxDelegate(self.interestTableView, self.interest_main_category_sel_list)
        self.interestTableView.setItemDelegateForColumn(1, mainCategorySelect)
        mainCategorySelect1 = ComboBoxDelegate(self.interestTableView, self.interest_main_category1_sel_list)
        self.interestTableView.setItemDelegateForColumn(2, mainCategorySelect1)
        mainCategorySelect2 = ComboBoxDelegate(self.interestTableView, self.interest_main_category2_sel_list)
        self.interestTableView.setItemDelegateForColumn(3, mainCategorySelect2)
        mainCategorySelect3 = ComboBoxDelegate(self.interestTableView, self.interest_main_category3_sel_list)
        self.interestTableView.setItemDelegateForColumn(4, mainCategorySelect3)

    def setOwner(self, owner):
        self.owner = owner
        self.newBot.setOwner(owner)

    def saveBot(self):
        self.main_win.showMsg("saving bot....")


        # if this bot already exists, then, this is an update case, else this is a new bot creation case.
        # if self.mode == "new":
        #    self.newBot = EBBOT()
        self.newBot.pubProfile.setPseudoName(self.pnn_edit.text())
        self.newBot.pubProfile.setLoc(self.loccity_edit.text() + "," + self.locstate_edit.text())
        if self.m_rb.isChecked():
            self.newBot.pubProfile.setPersonal("Male")
        elif self.f_rb.isChecked():
            self.newBot.pubProfile.setPersonal("Female")
        else:
            self.newBot.pubProfile.setPersonal("NA")

        self.newBot.pubProfile.setPseudoFirstLastName(self.pfn_edit.text(), self.pln_edit.text())
        self.newBot.privateProfile.setFirstLastName(self.fn_edit.text(), self.ln_edit.text())
        self.newBot.privateProfile.setAcct(self.em_edit.text(), self.empw_edit.text(), self.phone_edit.text(),
                                           self.backem_edit.text(), self.acctpw_edit.text(), self.backem_edit.text())

        self.newBot.pubProfile.setPubBirthday(self.bd_edit.text())
        self.newBot.pubProfile.setNickName(self.pnn_edit.text())
        self.newBot.settings.setComputer(self.os_sel.currentText(), self.machine_sel.currentText(),
                                         self.browser_sel.currentText())

        self.newBot.privateProfile.setAddr(self.addr_l1_edit.text(), self.addr_l2_edit.text(),
                                           self.addr_city_edit.text(), self.addr_state_edit.text(),
                                           self.addr_zip_edit.text())
        if self.shipaddr_same_checkbox.isChecked():
            self.shipaddr_l1_edit.setText(self.addr_l1_edit.text())
            self.shipaddr_l2_edit.setText(self.addr_l2_edit.text())
            self.shipaddr_city_edit.setText(self.addr_city_edit.text())
            self.shipaddr_state_edit.setText(self.addr_state_edit.text())
            self.shipaddr_zip_edit.setText(self.addr_zip_edit.text())

        self.newBot.privateProfile.setShippingAddr(self.shipaddr_l1_edit.text(), self.shipaddr_l2_edit.text(),
                                                   self.shipaddr_city_edit.text(), self.shipaddr_state_edit.text(),
                                                   self.shipaddr_zip_edit.text())
        print("set private addr:", self.addr_l1_edit.text(), self.addr_l2_edit.text(),
                                           self.addr_city_edit.text(), self.addr_state_edit.text(),
                                           self.addr_zip_edit.text())
        print("set shipping addr:", self.shipaddr_l1_edit.text(), self.shipaddr_l2_edit.text(),
                                                   self.shipaddr_city_edit.text(), self.shipaddr_state_edit.text(),
                                                   self.shipaddr_zip_edit.text())
        self.newBot.setStatus(self.state_select.currentText())
        self.newBot.updateDisplay()

        self.fillRoles()
        self.fillInterests()
        self.newBot.pubProfile.setVehicle(self.selected_vehicle_combo_box)
        # os = self.selected_vehicle_combo_box.split("-")[0]
        # roles = self.newBot.getRoles()
        # if os not in roles:
        #     msg_box = QMessageBox()
        #     msg_box.setIcon(QMessageBox.Critical)
        #     msg_box.setText(QApplication.translate("QMessageBox", "Login Error.  Try again..."))
        #     msg_box.setWindowTitle("Error")
        #     msg_box.exec_()
        # else:
        if self.mode == "new":
            self.main_win.showMsg("adding new bot....")
            self.main_win.addNewBots([self.newBot])
        elif self.mode == "update":
            self.main_win.showMsg("update a bot....")
            print("new bot:", self.newBot.getVehicle(), self.newBot.getInterests())
            self.main_win.updateBots([self.newBot])

        self.close()

    def fillRoles(self):
        self.newBot.setRoles("")
        self.newBot.setLevels("")
        rowCount = self.roleTableModel.rowCount()
        for i in range(rowCount):
            platform = self.roleTableModel.item(i, 0).text()
            level = self.roleTableModel.item(i, 1).text()
            role = self.roleTableModel.item(i, 2).text()
            role_words = platform + ":" + role
            level_words = platform + ":" + level + ":" + role
            if i == 0:
                self.newBot.setRoles(self.newBot.getRoles() + role_words)
                self.newBot.setLevels(self.newBot.getLevels() + level_words)
            else:
                self.newBot.setRoles(self.newBot.getRoles() + "," + role_words)
                self.newBot.setLevels(self.newBot.getLevels() + "," + level_words)
        self.main_win.showMsg("roles>>>>>" + json.dumps(self.newBot.getRoles()))

    def fillInterests(self):
        self.newBot.setInterests("")
        rowCount = self.interestTableModel.rowCount()
        print("interest table rows:", rowCount)
        for i in range(rowCount):
            if self.interestTableModel.item(i, 0):
                platform = self.interestTableModel.item(i, 0).text()
            else:
                platform = "any"

            if self.interestTableModel.item(i, 1):
                main_category = self.interestTableModel.item(i, 1).text()
            else:
                main_category = "any"

            if self.interestTableModel.item(i, 2):
                sub_category1 = self.interestTableModel.item(i, 2).text()
            else:
                sub_category1 = "any"

            if self.interestTableModel.item(i, 3):
                sub_category2 = self.interestTableModel.item(i, 3).text()
            else:
                sub_category2 = "any"

            if self.interestTableModel.item(i, 4):
                sub_category3 = self.interestTableModel.item(i, 4).text()
            else:
                sub_category3 = "any"

            int_words = platform + "|" + main_category + "|" + sub_category1 + "|" + sub_category2 + "|" + sub_category3
            if i == 0:
                self.newBot.setInterests(int_words)
            else:
                self.newBot.setInterests(self.newBot.getInterests() + "," + int_words)

            if self.interestTableModel.item(i, 0):
                break
        self.main_win.showMsg("interests>>>>>" + json.dumps(self.newBot.getInterests()))

    def selFile(self):
        # File actions
        fdir = self.fsel.getExistingDirectory()
        self.main_win.showMsg(fdir)
        return fdir

    def setMode(self, mode):
        self.mode = mode
        if self.mode == "new":
            self.setWindowTitle('Adding a new bot')
        elif self.mode == "update":
            self.setWindowTitle('Updating a new bot')

    def vehicle_combo_box_changed(self):
        self.selected_vehicle_combo_box = self.vehicle_combo_box.currentText().split("(")[0]

    def rolePlatformSel_changed(self):
        if self.role_platform_sel.currentText() != QApplication.translate("QComboBox", "Custom"):
            self.hide_role_custom_platform()
            self.selected_role_platform = self.role_platform_sel.currentText()
        else:
            self.show_role_custom_platform()
            self.selected_role_platform = self.role_custom_platform_edit.text()

    def roleLevelSel_changed(self):
        self.selected_role_level = self.role_level_sel.currentText()

    def roleNameSel_changed(self):
        self.selected_role_role = self.role_name_sel.currentText()

    def interestPlatformSel_changed(self):
        if self.interest_platform_sel.currentText() != 'Custom':
            self.hide_interest_custom_platform()
            self.selected_interest_platform = self.interest_platform_sel.currentText()
        else:
            self.show_interest_custom_platform()
            self.selected_interest_platform = self.interest_custom_platform_edit.text()

    def interestMainCategorySel_changed(self):
        if self.interest_main_category_sel.currentText() != 'Custom':
            self.hide_interest_custom_main_category()
            self.selected_interest_main_category = self.interest_main_category_sel.currentText()
        else:
            self.show_interest_custom_main_category()
            self.selected_interest_main_category = self.interest_custom_main_category_edit.text()

    def interestSubCategory1Sel_changed(self):
        if self.interest_sub_category1_sel.currentText() != 'Custom':
            self.hide_interest_custom_sub_category1()
            self.selected_interest_sub_category1 = self.interest_sub_category1_sel.currentText()
        else:
            self.show_interest_custom_sub_category1()
            self.selected_interest_sub_category1 = self.interest_custom_sub_category1_edit.text()

    def interestSubCategory2Sel_changed(self):
        if self.interest_sub_category2_sel.currentText() != 'Custom':
            self.hide_interest_custom_sub_category2()
            self.selected_interest_sub_category2 = self.interest_sub_category2_sel.currentText()
        else:
            self.show_interest_custom_sub_category2()
            self.selected_interest_sub_category2 = self.interest_custom_sub_category2_edit.text()

    def interestSubCategory3Sel_changed(self):
        if self.interest_sub_category3_sel.currentText() != 'Custom':
            self.hide_interest_custom_sub_category3()
            self.selected_interest_sub_category3 = self.interest_sub_category3_sel.currentText()
        else:
            self.show_interest_custom_sub_category3()
            self.selected_interest_sub_category3 = self.interest_custom_sub_category3_edit.text()

    def shipaddr_same_checkbox_toggled(self):
        if self.shipaddr_same_checkbox.isChecked():
            self.shipaddr_l1_edit.setText(self.addr_l1_edit.text())
            self.shipaddr_l2_edit.setText(self.addr_l2_edit.text())
            self.shipaddr_city_edit.setText(self.addr_city_edit.text())
            self.shipaddr_state_edit.setText(self.addr_state_edit.text())
            self.shipaddr_zip_edit.setText(self.addr_zip_edit.text())

    def _createRoleEditAction(self):
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Edit"))
        return new_action

    def _createRoleDeleteAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Delete"))
        return new_action

    def _createInterestEditAction(self):
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Edit"))
        return new_action

    def _createInterestDeleteAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Delete"))
        return new_action

    def createContextMenu(self, tableView, model):
        menu = QMenu(tableView)
        delete_action = QAction("Delete Row", self)
        delete_action.triggered.connect(lambda: self.deleteSelectedRow(tableView, model))
        menu.addAction(delete_action)
        return menu

    def eventFilter(self, obj, event):
        if obj in (self.roleTableView, self.interestTableView) and event.type() == QEvent.ContextMenu:
            if obj == self.roleTableView:
                self.roleMenu.popup(event.globalPos())
            elif obj == self.interestTableView:
                self.interestMenu.popup(event.globalPos())
            return True
        return super().eventFilter(obj, event)

    def findAllVehicle(self) -> List[VehicleModel]:
       return self.main_win.vehicle_service.findAllVehicle()

    def findVehicleByIp(self, ip) -> VehicleModel:
        return self.main_win.vehicle_service.find_vehicle_by_ip(ip)
    def deleteSelectedRow(self, tableView, model):
        reply = QMessageBox.question(self, '删除确认', '确定要删除这条记录吗？', QMessageBox.Yes | QMessageBox.No,
                                     QMessageBox.No)
        if reply == QMessageBox.Yes:
            indexes = tableView.selectionModel().selectedIndexes()
            if indexes:
                rows_to_delete = sorted(set(index.row() for index in indexes), reverse=True)
                for row in rows_to_delete:
                    model.removeRow(row)
