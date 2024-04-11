import sys
import random

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFont, QStandardItemModel
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QMainWindow, QFileDialog, QTabWidget, QScrollArea, \
    QVBoxLayout, QLineEdit, QRadioButton, QHBoxLayout, QComboBox, QCheckBox
from ebbot import *
from locale import getdefaultlocale
from FlowLayout import *
from ebbot import *



class RoleListView(QListView):
    def __init__(self, parent):
        super(RoleListView, self).__init__()
        self.selected_row = None
        self.parent = parent

    def mousePressEvent(self, e):
        if e.type() == QEvent.MouseButtonPress:
            if e.button() == Qt.LeftButton:
                print("row:", self.indexAt(e.pos()).row())
                self.selected_row = self.indexAt(e.pos()).row()
                self.parent.updateSelectedRole(self.selected_row)

class ROLE(QStandardItem):
    def __init__(self, platform, level, role, homepath):
        super().__init__()
        self.platform = platform
        self.level = level
        self.role = role
        self.name = platform+"_"+level+"_"+role

        self.setText(self.name)
        self.icon = QIcon(homepath+'/resource/images/icons/duty0-64.png')
        self.setIcon(self.icon)

    def getData(self):
        return self.platform, self.level, self.role

    def setPlatform(self, platform):
        self.platform = platform

    def setLevel(self, level):
        self.level = level

    def setRole(self, role):
        self.role = role

class InterestsListView(QListView):
    def __init__(self, parent):
        super(InterestsListView, self).__init__()
        self.selected_row = None
        self.parent = parent

    def mousePressEvent(self, e):
        if e.type() == QEvent.MouseButtonPress:
            if e.button() == Qt.LeftButton:
                print("row:", self.indexAt(e.pos()).row())
                self.selected_row = self.indexAt(e.pos()).row()
                self.parent.updateSelectedInterest(self.selected_row)

class INTEREST(QStandardItem):
    def __init__(self, homepath, platform, maincat, subcat1, subcat2="", subcat3="", subcat4="", subcat5=""):
        super().__init__()
        self.platform = platform
        self.homepath = homepath
        self.main_category = maincat
        self.sub_category1 = subcat1
        self.sub_category2 = subcat2
        self.sub_category3 = subcat3
        self.sub_category4 = subcat4
        self.sub_category5 = subcat5
        self.name = platform+"|"+maincat+"|"+subcat1
        if subcat2 != "" and subcat2 != "any":
            self.name = self.name + "|" + subcat2
        if subcat3 != "" and subcat3 != "any":
            self.name = self.name + "|" + subcat3
        if subcat4 != "" and subcat4 != "any":
            self.name = self.name + "|" + subcat4
        if subcat5 != "" and subcat5 != "any":
            self.name = self.name + "|" + subcat5

        self.setText(self.name)
        self.icon = QIcon(homepath+'/resource/images/icons/interests-64.png')
        self.setIcon(self.icon)

    def getData(self):
        return self.platform, self.main_category, self.sub_category1, self.sub_category2, self.sub_category3, self.sub_category4, self.sub_category5

# bot parameters:
# botid,owner,level,levelStart,gender,birthday,interests,location,roles,status,delDate
# note: level is in the format of: "site:level:role,site:level:role....."
#       levelStart is in the format of: "site:birthday:role,site:birthday:role....."
#       role is in the format: site:role, site:role      role can be "buyer"/"seller"/
class BotNewWin(QMainWindow):
    def __init__(self, parent):
        super(BotNewWin, self).__init__(parent)

        self.newBot = EBBOT(parent)

    # def __init__(self):
    #     super().__init__()
        self.mainWidget = QWidget()

        self.parent = parent
        self.homepath = parent.homepath

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


        self.roleListView = RoleListView(self)
        self.roleListView.installEventFilter(self)
        self.roleModel = QStandardItemModel(self.roleListView)

        self.roleListView.setModel(self.roleModel)
        self.roleListView.setViewMode(QListView.IconMode)
        self.roleListView.setMovement(QListView.Snap)

        self.roleScrollLabel = QLabel(QApplication.translate("QLabel", "Roles:"), alignment=Qt.AlignLeft)
        self.roleScroll = QScrollArea()
        self.roleScroll.setWidget(self.roleListView)
        self.roleScrollArea = QWidget()
        self.roleScrollLayout = QVBoxLayout(self)

        self.roleScrollLayout.addWidget(self.roleScrollLabel)
        self.roleScrollLayout.addWidget(self.roleScroll)
        self.roleScrollArea.setLayout(self.roleScrollLayout)

        #
        self.interestListView = InterestsListView(self)
        self.interestListView.installEventFilter(self)
        self.interestModel = QStandardItemModel(self.interestListView)

        self.interestListView.setModel(self.interestModel)
        self.interestListView.setViewMode(QListView.IconMode)
        self.interestListView.setMovement(QListView.Snap)

        self.interestScrollLabel = QLabel(QApplication.translate("QLabel", "Interests:"), alignment=Qt.AlignLeft)
        self.interestScroll = QScrollArea()
        self.interestScroll.setWidget(self.interestListView)
        self.interestScrollArea = QWidget()
        self.interestScrollLayout = QVBoxLayout(self)

        self.interestScrollLayout.addWidget(self.interestScrollLabel)
        self.interestScrollLayout.addWidget(self.interestScroll)
        self.interestScrollArea.setLayout(self.interestScrollLayout)

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
        self.loccity_label = QLabel(QApplication.translate("QLabel", "Location City:"), alignment=Qt.AlignLeft)
        self.loccity_edit = QLineEdit()
        self.loccity_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input City here"))
        self.locstate_label = QLabel(QApplication.translate("QLabel", "Location State:"), alignment=Qt.AlignLeft)
        self.locstate_edit = QLineEdit()
        self.locstate_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input State here"))
        self.age_label = QLabel(QApplication.translate("QLabel", "Age:"), alignment=Qt.AlignLeft)
        self.age_edit = QLineEdit()
        self.age_edit.setReadOnly(True)
        self.pfn_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input age here"))
        self.mf_label = QLabel(QApplication.translate("QLabel", "Gender:"), alignment=Qt.AlignLeft)

        self.bd_label = QLabel(QApplication.translate("QLabel", "Birthday:"), alignment=Qt.AlignLeft)
        self.bd_edit = QLineEdit()
        self.bd_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input in YYYY-MM-DD format"))

        self.m_rb = QRadioButton(QApplication.translate("QRadioButton", "Male"))
        self.f_rb = QRadioButton(QApplication.translate("QRadioButton", "Female"))
        self.gna_rb = QRadioButton(QApplication.translate("QRadioButton", "Unknown"))
        self.gna_rb.isChecked()

        self.interest_area_label = QLabel(QApplication.translate("QLabel", "Interests Area:"), alignment=Qt.AlignLeft)
        self.interest_platform_label = QLabel(QApplication.translate("QLabel", "Interests platform:"), alignment=Qt.AlignLeft)
        self.interest_platform_sel = QComboBox()
        self.interest_platform_sel.addItem(QApplication.translate("QComboBox", "any"))
        for p in self.parent.getSITES():
            self.interest_platform_sel.addItem(QApplication.translate("QComboBox", p))
        self.interest_platform_sel.currentTextChanged.connect(self.interestPlatformSel_changed)
        self.interest_main_category_label = QLabel(QApplication.translate("QLabel", "Interest Main Category:"), alignment=Qt.AlignLeft)
        self.interest_main_category_sel = QComboBox()
        self.interest_main_category_sel.addItem(QApplication.translate("QComboBox", "any"))
        self.interest_main_category_sel.addItem(QApplication.translate("QComboBox", "custom"))
        self.interest_main_category_sel.currentTextChanged.connect(self.interestMainCategorySel_changed)


        self.interest_sub_category1_label = QLabel(QApplication.translate("QLabel", "Interest Sub Category1:"), alignment=Qt.AlignLeft)
        self.interest_sub_category1_sel = QComboBox()
        self.interest_sub_category1_sel.addItem(QApplication.translate("QComboBox", "any"))
        self.interest_sub_category1_sel.addItem(QApplication.translate("QComboBox", "custom"))
        self.interest_sub_category1_sel.currentTextChanged.connect(self.interestSubCategory1Sel_changed)


        self.interest_sub_category2_label = QLabel(QApplication.translate("QLabel", "Interest Sub Category2:"), alignment=Qt.AlignLeft)
        self.interest_sub_category2_sel = QComboBox()
        self.interest_sub_category2_sel.addItem(QApplication.translate("QComboBox", "any"))
        self.interest_sub_category2_sel.addItem(QApplication.translate("QComboBox", "custom"))
        self.interest_sub_category2_sel.currentTextChanged.connect(self.interestSubCategory2Sel_changed)

        self.interest_sub_category3_label = QLabel(QApplication.translate("QLabel", "Interest Sub Category3:"), alignment=Qt.AlignLeft)
        self.interest_sub_category3_sel = QComboBox()
        self.interest_sub_category3_sel.addItem(QApplication.translate("QComboBox", "any"))
        self.interest_sub_category3_sel.addItem(QApplication.translate("QComboBox", "custom"))
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
        self.interest_custom_platform_label = QLabel(QApplication.translate("QLabel", "Interest Custom platform:"), alignment=Qt.AlignLeft)
        self.interest_custom_platform_edit = QLineEdit()
        self.interest_custom_main_category_label = QLabel(QApplication.translate("QLabel", "Interest Custom Main Category:"), alignment=Qt.AlignLeft)
        self.interest_custom_main_category_edit = QLineEdit()
        self.interest_custom_sub_category1_label = QLabel(QApplication.translate("QLabel", "Interest Custom Main Sub Category1:"), alignment=Qt.AlignLeft)
        self.interest_custom_sub_category1_edit = QLineEdit()
        self.interest_custom_sub_category2_label = QLabel(QApplication.translate("QLabel", "Interest Custom Main Sub Category2:"), alignment=Qt.AlignLeft)
        self.interest_custom_sub_category2_edit = QLineEdit()
        self.interest_custom_sub_category3_label = QLabel(QApplication.translate("QLabel", "Interest Custom Main Sub Category3:"), alignment=Qt.AlignLeft)
        self.interest_custom_sub_category3_edit = QLineEdit()
        # self.interest_custom_sub_category4_label = QLabel(QApplication.translate("QLabel", "Interest Custom Main Sub Category4:"), alignment=Qt.AlignLeft)
        # self.interest_custom_sub_category4_edit = QLineEdit()
        # self.interest_custom_sub_category5_label = QLabel(QApplication.translate("QLabel", "Interest Custom Main Sub Category5:"), alignment=Qt.AlignLeft)
        # self.interest_custom_sub_category5_edit = QLineEdit()

        self.role_platform_label = QLabel(QApplication.translate("QLabel", "Platform:"), alignment=Qt.AlignLeft)
        self.role_platform_edit = QLineEdit()
        self.role_platform_sel = QComboBox()
        for p in self.parent.getSITES():
            self.role_platform_sel.addItem(QApplication.translate("QComboBox", p))

        self.role_platform_sel.currentTextChanged.connect(self.rolePlatformSel_changed)
        self.role_custom_platform_label = QLabel(QApplication.translate("QLabel", "Custom Platform:"), alignment=Qt.AlignLeft)
        self.role_custom_platform_edit = QLineEdit()
        self.role_level_label = QLabel(QApplication.translate("QLabel", "Level:"), alignment=Qt.AlignLeft)
        self.role_level_edit = QLineEdit()
        self.role_level_sel = QComboBox()
        self.role_level_sel.addItem(QApplication.translate("QComboBox", "Green"))
        QApplication.translate("QComboBox", "Champ")
        self.role_level_sel.addItem(QApplication.translate("QComboBox", "Experienced"))
        self.role_level_sel.addItem(QApplication.translate("QComboBox", "Expert"))
        self.role_level_sel.addItem(QApplication.translate("QComboBox", "Master"))
        self.role_level_sel.addItem(QApplication.translate("QComboBox", "Champ"))
        self.role_level_sel.currentTextChanged.connect(self.roleLevelSel_changed)
        self.role_name_label = QLabel(QApplication.translate("QLabel", "Role:"), alignment=Qt.AlignLeft)
        self.role_name_edit = QLineEdit()
        self.role_name_sel = QComboBox()
        self.role_name_sel.addItem(QApplication.translate("QComboBox", "Buyer"))
        self.role_name_sel.addItem(QApplication.translate("QComboBox", "Seller"))
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
        self.pubpflWidget_layout.addWidget(self.interestScrollArea)


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

        self.pubpflWidget_layout.addWidget(self.roleScrollArea)

        # self.pubpflLine8Layout = QHBoxLayout(self)
        # self.pubpflLine8Layout.addWidget(self.pnn_label)
        # self.pubpflLine8Layout.addWidget(self.pnn_edit)
        # self.pubpflWidget.layout.addLayout(self.pubpflLine8Layout)

        self.pubpflWidget.setLayout(self.pubpflWidget_layout)


        self.fn_label = QLabel(QApplication.translate("QLabel", "First Name:"), alignment=Qt.AlignLeft)
        self.fn_edit = QLineEdit()

        self.fn_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input First Name here"))
        self.ln_label = QLabel(QApplication.translate("QLabel", "Last Name:"), alignment=Qt.AlignLeft)
        self.ln_edit = QLineEdit()
        self.ln_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input Last Name here"))


        self.addr_label = QLabel(QApplication.translate("QLabel", "Address:"), alignment=Qt.AlignLeft)
        self.shipaddr_label = QLabel(QApplication.translate("QLabel", "Shipping Address:"), alignment=Qt.AlignLeft)
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

        self.shipaddr_same_label = QLabel(QApplication.translate("QLabel", "Shipping Address Same As Address?"), alignment=Qt.AlignLeft)
        self.shipaddr_same_checkbox = QCheckBox()
        self.shipaddr_same_checkbox.setCheckState(Qt.CheckState.Unchecked)
        self.shipaddr_same_checkbox.stateChanged.connect(self.shipaddr_same_checkbox_toggled)

        self.shipaddr_l1_label = QLabel(QApplication.translate("QLabel", "Shipping Address Line1:"), alignment=Qt.AlignLeft)
        self.shipaddr_l1_edit = QLineEdit()

        self.shipaddr_l2_label = QLabel(QApplication.translate("QLabel", "Shipping Address Line2:"), alignment=Qt.AlignLeft)
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
        self.em_label = QLabel(QApplication.translate("QLabel", "User Email:"), alignment=Qt.AlignLeft)
        self.em_edit = QLineEdit()
        self.em_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input email here"))
        self.empw_label = QLabel(QApplication.translate("QLabel", "Email Password:"), alignment=Qt.AlignLeft)
        self.empw_edit = QLineEdit()
        self.empw_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input Email Password here"))
        self.backem_label = QLabel(QApplication.translate("QLabel", "Back Up Email:"), alignment=Qt.AlignLeft)
        self.backem_edit = QLineEdit()
        self.backem_edit.setPlaceholderText(QApplication.translate("QLineEdit", "(optional) back up email here"))
        self.acctpw_label = QLabel(QApplication.translate("QLabel", "E-Business Account Password:"), alignment=Qt.AlignLeft)
        self.acctpw_edit = QLineEdit("")
        self.acctpw_edit.setPlaceholderText(QApplication.translate("QLineEdit", "(optional) E-Business Account Password here"))
        self.backem_site_label = QLabel(QApplication.translate("QLabel", "Backup Email Site:"), alignment=Qt.AlignLeft)
        self.backem_site_edit = QLineEdit("")
        self.backem_site_edit.setPlaceholderText(QApplication.translate("QLineEdit", "website for access backup email"))

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
        for app in self.parent.getAPPS():
            self.browser_sel.addItem(QApplication.translate("QComboBox", app))

        self.os_label = QLabel(QApplication.translate("QLabel", "OS Type:"), alignment=Qt.AlignLeft)
        self.os_sel = QComboBox()
        for cos in self.parent.getPLATFORMS():
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

        self.state_label = QLabel(QApplication.translate("QLabel", "Enabled:"), alignment=Qt.AlignLeft)
        self.state_en = QCheckBox()
        self.state_en.setCheckState(Qt.CheckState.Checked)


        self.statLine1Layout = QHBoxLayout(self)
        self.statLine1Layout.addWidget(self.state_label)
        self.statLine1Layout.addWidget(self.state_en)
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

    def saveRole(self):
        if self.role_platform_sel.currentText() == QApplication.translate("QComboBox", "Custom"):
            self.selected_role_platform = self.role_custom_platform_edit.text()

        self.newRole = ROLE(self.selected_role_platform, self.selected_role_level, self.selected_role_role, self.homepath)
        self.roleModel.appendRow(self.newRole)

        rw = ""
        lvl = ""
        for ri in range(self.roleModel.rowCount()):

            r = self.roleModel.item(ri)
            rw = rw + r.platform + ":" + r.role
            lvl = lvl + r.platform + ":" + r.role + ":" + r.level
            if ri != self.roleModel.rowCount()-1:
                rw = rw + ","
                lvl = lvl + ","
        self.newBot.setRoles(rw)
        self.newBot.setLevels(lvl)


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

        self.newInterest = INTEREST(self.selected_interest_platform, self.selected_interest_main_category, self.selected_interest_sub_category1, self.selected_interest_sub_category2, self.selected_interest_sub_category3, self.selected_interest_sub_category4, self.selected_interest_sub_category5)
        self.interestModel.appendRow(self.newInterest)

        interests = ""
        for ri in range(self.interestModel.rowCount()):
            r = self.interestModel.item(ri)
            interests = interests + r.name
            if ri != self.interestModel.rowCount():
                interests = interests + ","
        self.newBot.setInterests(interests)

    # fill GUI from data.
    def setBot(self, bot):
        self.newBot = bot
        #now populate the GUI to reflect info in this bot.
        self.acctpw_edit.setText(bot.getAcctPw())
        self.age_edit.setText(str(bot.getAge()))
        self.bd_edit.setText(bot.getPubBirthday())
        self.backem_edit.setText(bot.getBackEm())
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
        print("hihii???")
        # self.pnn_edit.setText(bot.getNickName())
        self.phone_edit.setText(bot.getPhone())
        # self.icon_path_edit.setText(bot.getIconLink())
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
        else:
            self.shipaddr_same_checkbox.setChecked(False)

        self.shipaddr_l1_edit.setText(bot.getShippingAddrStreet1())
        self.shipaddr_l2_edit.setText(bot.getShippingAddrStreet2())
        self.shipaddr_city_edit.setText(bot.getShippingAddrCity())
        self.shipaddr_state_edit.setText(bot.getShippingAddrState())
        self.shipaddr_zip_edit.setText(bot.getShippingAddrZip())

        self.loadRoles(bot)
        self.loadInterests(bot)

    def loadRoles(self, bot):
        rp_options = ['Amazon', 'Etsy', 'Ebay']
        rl_options = ['green', 'experienced', 'expert']
        rr_options = ['Buyer', 'Seller']
        all_roles = bot.getLevels()
        if all_roles != "":
            roles = all_roles.split(",")
            print("ROLES:", roles)
            if len(roles) > 0:
                role_parts = roles[0].split(":")
                role_platform = role_parts[0]
                role_level = role_parts[2]
                role_role = role_parts[1]

                if role_platform in rp_options:
                    self.role_platform_sel.setCurrentText(role_platform)
                else:
                    self.role_platform_sel.setCurrentText('Custom')
                    self.role_custom_platform_edit.setText(role_platform)

                if role_level in rl_options:
                    self.role_level_sel.setCurrentText(role_level)
                else:
                    self.role_level_sel.setCurrentText('Custom')
                    self.role_level_edit.setText(role_level)

                if role_role in rr_options:
                    self.role_name_sel.setCurrentText(role_role)
                else:
                    self.role_name_sel.setCurrentText('Custom')
                    self.role_name_edit.setText(role_level)

            for role in roles:
                self.newRole = ROLE(role_platform, role_level, role_role, self.homepath)
                self.roleModel.appendRow(self.newRole)

            self.selected_role_row = 0
            self.selected_role_item = self.roleModel.item(self.selected_role_row)


    def loadInterests(self, bot):
        intp_options = ['Amazon', 'Etsy', 'Ebay', 'any']
        imc_options = ['any']
        isc1_options = ['any']
        isc2_options = ['any']
        isc3_options = ['any']
        print("bot intests:", bot.getInterests())
        all_ints = bot.getInterests()

        if all_ints != "":
            ints = all_ints.split(",")
            print("ints:", ints)

            if len(ints) > 0:
                if ints[0] == "":
                    top_int = ints[1]
                else:
                    top_int = ints[0]
                int_parts = top_int.split("|")
                print("int_parts:", int_parts)
                int_platform = int_parts[0]
                print("int_platform:", int_platform)
                if len(int_parts)>1:
                    int_mc = int_parts[1]
                else:
                    int_mc = "any"
                print("int_mc:", int_mc)
                if len(int_parts)>2:
                    int_sc1 = int_parts[2]
                else:
                    int_sc1 = "any"
                print("int_sc1:", int_sc1)
                if len(int_parts)>3:
                    int_sc2 = int_parts[3]
                else:
                    int_sc2 = "any"
                print("int_sc2:", int_sc2)
                if len(int_parts)>4:
                    int_sc3 = int_parts[4]
                else:
                    int_sc3 = "any"
                print("getting all int parts.", int_sc3)
                if int_platform in intp_options:
                    self.interest_platform_sel.setCurrentText(int_platform)
                else:
                    self.interest_platform_sel.setCurrentText('custom')
                    self.interest_custom_platform_edit.setText(int_platform)

                if int_mc in imc_options:
                    self.interest_main_category_sel.setCurrentText(int_mc)
                else:
                    self.interest_main_category_sel.setCurrentText('custom')
                    self.interest_custom_main_category_edit.setText(int_mc)

                if int_sc1 in isc1_options:
                    self.interest_sub_category1_sel.setCurrentText(int_sc1)
                else:
                    self.interest_sub_category1_sel.setCurrentText('custom')
                    self.interest_custom_sub_category1_edit.setText(int_sc1)

                if int_sc2 in isc2_options:
                    self.interest_sub_category2_sel.setCurrentText(int_sc2)
                else:
                    self.interest_sub_category2_sel.setCurrentText('custom')
                    self.interest_custom_sub_category2_edit.setText(int_sc2)

                if int_sc3 in isc3_options:
                    self.interest_sub_category3_sel.setCurrentText(int_sc3)
                else:
                    self.interest_sub_category3_sel.setCurrentText('custom')
                    self.interest_custom_sub_category3_edit.setText(int_sc3)

            for aint in ints:
                self.newInterest = INTEREST(int_platform, int_mc, int_sc1, int_sc2, int_sc3, "Any", "Any")
                self.interestModel.appendRow(self.newInterest)

            self.selected_interest_row = 0
            self.selected_interest_item = self.interestModel.item(self.selected_interest_row)

        print("bot intests loaded......")


    def setOwner(self, owner):
        self.owner = owner
        self.newBot.setOwner(owner)

    def saveBot(self):
        print("saving bot....")
        # if this bot already exists, then, this is an update case, else this is a new bot creation case.
        #if self.mode == "new":
        #    self.newBot = EBBOT(self)
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
        self.newBot.privateProfile.setAcct(self.em_edit.text(), self.empw_edit.text(), self.phone_edit.text(), self.backem_edit.text(), self.acctpw_edit.text(), self.backem_edit.text())

        self.newBot.pubProfile.setPubBirthday(self.bd_edit.text())
        self.newBot.pubProfile.setNickName(self.pnn_edit.text())


        self.newBot.settings.setComputer(self.os_sel.currentText(), self.machine_sel.currentText(), self.browser_sel.currentText())

        self.newBot.privateProfile.setAddr(self.addr_l1_edit.text(), self.addr_l2_edit.text(), self.addr_city_edit.text(), self.addr_state_edit.text(), self.addr_zip_edit.text())
        self.newBot.privateProfile.setShippingAddr(self.shipaddr_l1_edit.text(), self.shipaddr_l2_edit.text(), self.shipaddr_city_edit.text(), self.shipaddr_state_edit.text(), self.shipaddr_zip_edit.text())

        self.fillRoles()
        self.fillInterests()

        if self.mode == "new":
            print("adding new bot....")
            self.parent.addNewBots([self.newBot])
        elif self.mode == "update":
            print("update a bot....")
            self.parent.updateBots([self.newBot])

        self.close()
        # print(self.parent)

    def fillRoles(self):
        self.newBot.setRoles("")
        for i in range(self.roleModel.rowCount()):
            self.selected_role_item = self.roleModel.item(i)
            rd = self.selected_role_item.getData()
            role_words = rd[0] + ":" + rd[2]
            if i == 0:
                self.newBot.setRoles(self.newBot.getRoles() + role_words)
            else:
                self.newBot.setRoles(self.newBot.getRoles() + "," + role_words)
            print("roles>>>>>", self.newBot.getRoles())

    def fillInterests(self):
        self.newBot.setInterests("")
        for i in range(self.interestModel.rowCount()):
            self.selected_interest_item = self.interestModel.item(i)
            intd = self.selected_interest_item.getData()
            int_words = intd[0] + "|" + intd[1] + "|" + intd[2] + "|" + intd[3] + "|" + intd[4]
            if i == 0:
                self.newBot.setInterests(self.newBot.getInterests() + int_words)
            else:
                self.newBot.setInterests(self.newBot.getInterests() + "," + int_words)
            print("interests>>>>>", self.newBot.getInterests())

    def selFile(self):
        # File actions
        fdir = self.fsel.getExistingDirectory()
        print(fdir)
        return fdir

    def setMode(self, mode):
        self.mode = mode
        if self.mode == "new":
            self.setWindowTitle('Adding a new bot')
        elif self.mode == "update":
            self.setWindowTitle('Updating a new bot')

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


    # def interestSubCategory4Sel_changed(self):
    #     if self.interest_sub_category4_sel.currentText() != 'Custom':
    #         self.hide_interest_custom_sub_category4()
    #         self.selected_interest_sub_category4 = self.interest_sub_category4_sel.currentText()
    #     else:
    #         self.show_interest_custom_sub_category4()
    #         self.selected_interest_sub_category4 = self.interest_custom_sub_category4_edit.text()
    #
    # def interestSubCategory5Sel_changed(self):
    #     if self.interest_sub_category5_sel.currentText() != 'Custom':
    #         self.hide_interest_custom_sub_category5()
    #         self.selected_interest_sub_category5 = self.interest_sub_category5_sel.currentText()
    #     else:
    #         self.show_interest_custom_sub_category5()
    #         self.selected_interest_sub_category5 = self.interest_custom_sub_category5_edit.text()


    def updateSelectedInterest(self, row):
        self.selected_interest_row = row
        self.selected_interest_item = self.interestModel.item(self.selected_interest_row)
        platform, main_cat, sub_cat1, sub_cat2, sub_cat3, sub_cat4, sub_cat5 = self.selected_interest_item.getData()

        #update platform
        if self.interest_platform_sel.findText(platform) < 0:
            self.interest_platform_sel.setCurrentText("Custom")
            self.interest_custom_platform_edit.setText(platform)

        else:
            self.interest_platform_sel.setCurrentText(platform)
            self.interest_custom_platform_edit.setText("")

        # update main cat
        if self.interest_main_category_sel.findText(main_cat) < 0:
            self.interest_main_category_sel.setCurrentText("Custom")
            self.interest_custom_main_category_edit.setText(platform)

        else:
            self.interest_main_category_sel.setCurrentText(main_cat)
            self.interest_custom_main_category_edit.setText("")

        # update sub cat 1
        if self.interest_sub_category1_sel.findText(sub_cat1) < 0:
            self.interest_sub_category1_sel.setCurrentText("Custom")
            self.interest_custom_sub_category1_edit.setText(platform)

        else:
            self.interest_sub_category1_sel.setCurrentText(sub_cat1)
            self.interest_custom_sub_category1_edit.setText("")

        # update sub cat 2
        if self.interest_sub_category1_sel.findText(sub_cat1) < 0:
            self.interest_sub_category1_sel.setCurrentText("Custom")
            self.interest_custom_sub_category1_edit.setText(platform)

        else:
            self.interest_sub_category1_sel.setCurrentText(sub_cat1)
            self.interest_custom_sub_category1_edit.setText("")

        # update sub cat 3
        if self.interest_sub_category3_sel.findText(sub_cat3) < 0:
            self.interest_sub_category3_sel.setCurrentText("Custom")
            self.interest_custom_sub_category3_edit.setText(sub_cat3)

        else:
            self.interest_sub_category3_sel.setCurrentText(sub_cat3)
            self.interest_custom_sub_category3_edit.setText("")

        # # update sub cat 4
        # if self.interest_sub_category4_sel.findText(sub_cat4) < 0:
        #     self.interest_sub_category4_sel.setCurrentText("Custom")
        #     self.interest_custom_sub_category4_edit.setText(sub_cat4)
        #
        # else:
        #     self.interest_sub_category4_sel.setCurrentText(sub_cat4)
        #     self.interest_custom_sub_category4_edit.setText("")
        #
        # # update sub cat 5
        # if self.interest_sub_category5_sel.findText(sub_cat5) < 0:
        #     self.interest_sub_category5_sel.setCurrentText("Custom")
        #     self.interest_custom_sub_category5_edit.setText(sub_cat5)
        #
        # else:
        #     self.interest_sub_category5_sel.setCurrentText(sub_cat5)
        #     self.interest_custom_sub_category5_edit.setText("")
        #

    def updateSelectedRole(self, row):
        self.selected_role_row = row
        self.selected_role_item = self.roleModel.item(self.selected_role_row)
        platform, level, role = self.selected_role_item.getData()

        self.role_level_sel.setCurrentText(level)
        self.role_name_sel.setCurrentText(role)

        if self.role_platform_sel.findText(platform) < 0:
            self.role_platform_sel.setCurrentText("Custom")
            self.role_custom_platform_edit.setText(platform)

        else:
            self.role_platform_sel.setCurrentText(platform)
            self.role_custom_platform_edit.setText("")


    def shipaddr_same_checkbox_toggled(self):
        if self.shipaddr_same_checkbox.isChecked():
            self.shipaddr_l1_edit.setText(self.addr_l1_edit.text())
            self.shipaddr_l2_edit.setText(self.addr_l2_edit.text())
            self.shipaddr_city_edit.setText(self.addr_city_edit.text())
            self.shipaddr_state_edit.setText(self.addr_state_edit.text())
            self.shipaddr_zip_edit.setText(self.addr_zip_edit.text())

    def eventFilter(self, source, event):
        if event.type() == QEvent.ContextMenu and source is self.roleListView:
            print("role menu....", source)
            self.popMenu = QMenu(self)
            self.pop_menu_font = QFont("Helvetica", 10)
            self.popMenu.setFont(self.pop_menu_font)

            self.roleEditAction = self._createRoleEditAction()
            self.roleDeleteAction = self._createRoleDeleteAction()

            self.popMenu.addAction(self.roleEditAction)
            self.popMenu.addSeparator()
            self.popMenu.addAction(self.roleDeleteAction)

            selected_act = self.popMenu.exec_(event.globalPos())
            if selected_act:
                self.selected_role_row = source.indexAt(event.pos()).row()
                self.selected_role_item = self.roleModel.item(self.selected_role_row)
                if selected_act == self.roleEditAction:
                    self.editRole()
                elif selected_act == self.roleDeleteAction:
                    self.deleteRole()
            return True
        elif event.type() == QEvent.ContextMenu and source is self.interestListView:
            print("interest menu....")
            self.popMenu = QMenu(self)
            self.pop_menu_font = QFont("Helvetica", 10)
            self.popMenu.setFont(self.pop_menu_font)
            self.interestEditAction = self._createInterestEditAction()
            self.interestDeleteAction = self._createInterestDeleteAction()

            self.popMenu.addAction(self.interestEditAction)
            self.popMenu.addSeparator()
            self.popMenu.addAction(self.interestDeleteAction)

            selected_act = self.popMenu.exec_(event.globalPos())
            if selected_act:
                self.selected_interest_row = source.indexAt(event.pos()).row()
                self.selected_interest_item = self.interestModel.item(self.selected_interest_row)
                if selected_act == self.interestEditAction:
                    self.editInterest()
                elif selected_act == self.interestDeleteAction:
                    self.deleteInterest()
            return True
        # else:
        #     print("unknwn.... RC menu....", source, " EVENT: ", event)
        return super().eventFilter(source, event)


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


    def editRole(self):
        if self.role_platform_sel.currentText() == "Custom":
            self.selected_role_item.setPlatform(self.role_platform_edit.text())
        else:
            self.selected_role_item.setPlatform(self.role_platform_sel.currentText())

        self.selected_role_item.setRole(self.role_level_sel.currentText())
        self.selected_role_item.setLevel(self.role_level_sel.currentText())


    def deleteRole(self):
        items = [self.selected_role_item]
        if len(items):
            for item in items:
                # remove file first, then the item in the model.
                # shutil.rmtree(temp_page_dir)
                # os.remove(full_temp_page)

                # remove the local data and GUI.
                self.roleModel.removeRow(item.row())

    def editInterest(self):
        print("")

    def deleteInterest(self):
        items = [self.selected_interest_item]
        if len(items):
            for item in items:
                # remove file first, then the item in the model.
                # shutil.rmtree(temp_page_dir)
                # os.remove(full_temp_page)

                # remove the local data and GUI.
                self.interestModel.removeRow(item.row())