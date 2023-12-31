import sys
import random
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import QApplication, QWidget, QPushButton
from ebbot import *
from locale import getdefaultlocale
from FlowLayout import *
from ebbot import *
from datetime import datetime



class RoleListView(QtWidgets.QListView):
    def __init__(self, parent):
        super(RoleListView, self).__init__()
        self.selected_row = None
        self.parent = parent

    def mousePressEvent(self, e):
        if e.type() == QtCore.QEvent.MouseButtonPress:
            if e.button() == QtCore.Qt.LeftButton:
                print("row:", self.indexAt(e.pos()).row())
                self.selected_row = self.indexAt(e.pos()).row()
                self.parent.updateSelectedRole(self.selected_row)

class ROLE(QtGui.QStandardItem):
    def __init__(self, platform, level, role, homepath):
        super().__init__()
        self.platform = platform
        self.homepath = homepath
        self.level = level
        self.role = role
        self.name = platform+"_"+level+"_"+role

        self.setText(self.name)
        self.icon = QtGui.QIcon(homepath+'/resource/images/icons/duty0-64.png')
        self.setIcon(self.icon)

    def getData(self):
        return self.platform, self.level, self.role


class InterestsListView(QtWidgets.QListView):
    def __init__(self, parent):
        super(InterestsListView, self).__init__()
        self.selected_row = None
        self.parent = parent

    def mousePressEvent(self, e):
        if e.type() == QtCore.QEvent.MouseButtonPress:
            if e.button() == QtCore.Qt.LeftButton:
                print("row:", self.indexAt(e.pos()).row())
                self.selected_row = self.indexAt(e.pos()).row()
                self.parent.updateSelectedInterest(self.selected_row)

class INTEREST(QtGui.QStandardItem):
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
        if subcat2 != "" and subcat2 != "ANY":
            self.name = self.name + "|" + subcat2
        if subcat3 != "" and subcat3 != "ANY":
            self.name = self.name + "|" + subcat3
        if subcat4 != "" and subcat4 != "ANY":
            self.name = self.name + "|" + subcat4
        if subcat5 != "" and subcat5 != "ANY":
            self.name = self.name + "|" + subcat5

        self.setText(self.name)
        self.icon = QtGui.QIcon(homepath+'/resource/images/icons/interests-64.png')
        self.setIcon(self.icon)

    def getData(self):
        return self.platform, self.main_category, self.sub_category1, self.sub_category2, self.sub_category3, self.sub_category4, self.sub_category5

# bot parameters:
# botid,owner,level,levelStart,gender,birthday,interests,location,roles,status,delDate
# note: level is in the format of: "site:level:role,site:level:role....."
#       levelStart is in the format of: "site:birthday:role,site:birthday:role....."
#       role is in the format: site:role, site:role      role can be "buyer"/"seller"/
class BotNewWin(QtWidgets.QMainWindow):
    def __init__(self, parent):
        super(BotNewWin, self).__init__(parent)

        self.newBot = EBBOT(parent)

    # def __init__(self):
    #     super().__init__()
        self.mainWidget = QtWidgets.QWidget()
        self.parent = parent
        self.homepath = parent.homepath

        self.text = QtWidgets.QApplication.translate("QtWidgets.QWidget", "new bot")
        self.pubpflWidget = QtWidgets.QWidget()
        self.prvpflWidget = QtWidgets.QWidget()
        self.setngsWidget = QtWidgets.QWidget()
        self.statWidget = QtWidgets.QWidget()
        self.tabs = QtWidgets.QTabWidget()
        self.actionFrame = QtWidgets.QFrame()

        self.selected_interest_platform = "Amazon"
        self.selected_interest_main_category = "Any"
        self.selected_interest_sub_category1 = "Any"
        self.selected_interest_sub_category2 = "Any"
        self.selected_interest_sub_category3 = "Any"
        self.selected_interest_sub_category4 = "Any"
        self.selected_interest_sub_category5 = "Any"



        self.selected_role_platform = "Amazon"
        self.selected_role_level = "Green"
        self.selected_role_role = "Buyer"

        self.fsel = QtWidgets.QFileDialog()
        self.mode = "new"

        self.roleListView = RoleListView(self)
        self.roleListView.installEventFilter(self)
        self.roleModel = QtGui.QStandardItemModel(self.roleListView)

        self.roleListView.setModel(self.roleModel)
        self.roleListView.setViewMode(QtWidgets.QListView.IconMode)
        self.roleListView.setMovement(QtWidgets.QListView.Snap)

        self.roleScrollLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Roles:"), alignment=QtCore.Qt.AlignLeft)
        self.roleScroll = QtWidgets.QScrollArea()
        self.roleScroll.setWidget(self.roleListView)
        self.roleScrollArea = QtWidgets.QWidget()
        self.roleScrollLayout = QtWidgets.QVBoxLayout(self)

        self.roleScrollLayout.addWidget(self.roleScrollLabel)
        self.roleScrollLayout.addWidget(self.roleScroll)
        self.roleScrollArea.setLayout(self.roleScrollLayout)

        #
        self.interestListView = InterestsListView(self)
        self.interestListView.installEventFilter(self)
        self.interestModel = QtGui.QStandardItemModel(self.interestListView)

        self.interestListView.setModel(self.interestModel)
        self.interestListView.setViewMode(QtWidgets.QListView.IconMode)
        self.interestListView.setMovement(QtWidgets.QListView.Snap)

        self.interestScrollLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Interests:"), alignment=QtCore.Qt.AlignLeft)
        self.interestScroll = QtWidgets.QScrollArea()
        self.interestScroll.setWidget(self.interestListView)
        self.interestScrollArea = QtWidgets.QWidget()
        self.interestScrollLayout = QtWidgets.QVBoxLayout(self)

        self.interestScrollLayout.addWidget(self.interestScrollLabel)
        self.interestScrollLayout.addWidget(self.interestScroll)
        self.interestScrollArea.setLayout(self.interestScrollLayout)

        self.role_save_button = QtWidgets.QPushButton(QtWidgets.QApplication.translate("QtWidgets.QPushButton", "Save Role"))
        self.interest_save_button = QtWidgets.QPushButton(QtWidgets.QApplication.translate("QtWidgets.QPushButton", "Save Interest"))
        self.save_button = QtWidgets.QPushButton(QtWidgets.QApplication.translate("QtWidgets.QPushButton", "Save"))
        self.cancel_button = QtWidgets.QPushButton(QtWidgets.QApplication.translate("QtWidgets.QPushButton", "Cancel"))
        self.text = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Hello World"), alignment=QtCore.Qt.AlignCenter)

        self.layout = QtWidgets.QVBoxLayout(self)
        self.bLayout = QtWidgets.QHBoxLayout(self)
        self.bLayout.addWidget(self.cancel_button)
        self.bLayout.addWidget(self.save_button)


        self.pubpflWidget_layout = QtWidgets.QVBoxLayout(self)
        self.prvpflWidget_layout = QtWidgets.QVBoxLayout(self)
        self.setngsWidget_layout = QtWidgets.QVBoxLayout(self)
        self.statWidget_layout = QtWidgets.QVBoxLayout(self)

        self.tag_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Tag:"), alignment=QtCore.Qt.AlignLeft)
        self.tag_edit = QtWidgets.QLineEdit("")

        self.tag_edit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "input bot tag here"))
        self.icon_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Icon Image:"))
        self.icon_path_edit = QtWidgets.QLineEdit("")
        self.icon_path_edit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "input icon img file path here"))

        self.icon_fs_button = QtWidgets.QPushButton("...")
        self.icon_fs_button.clicked.connect(self.selFile)

        # needs to add icon for better UE

        self.pfn_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Pseudo First Name:"), alignment=QtCore.Qt.AlignLeft)
        self.pfn_edit = QtWidgets.QLineEdit()
        self.pfn_edit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "input Pseudo First Name here"))
        self.pln_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Pseudo Last Name:"), alignment=QtCore.Qt.AlignLeft)
        self.pln_edit = QtWidgets.QLineEdit()
        self.pln_edit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "input Pseudo Last Name here"))
        self.pnn_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Pseudo Nick Name:"), alignment=QtCore.Qt.AlignLeft)
        self.pnn_edit = QtWidgets.QLineEdit()
        self.pnn_edit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "input Pseudo Nick Name here"))
        self.loccity_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Location City:"), alignment=QtCore.Qt.AlignLeft)
        self.loccity_edit = QtWidgets.QLineEdit()
        self.loccity_edit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "input City here"))
        self.locstate_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Location State:"), alignment=QtCore.Qt.AlignLeft)
        self.locstate_edit = QtWidgets.QLineEdit()
        self.locstate_edit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "input State here"))
        self.age_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Age:"), alignment=QtCore.Qt.AlignLeft)
        self.age_edit = QtWidgets.QLineEdit()
        self.pfn_edit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "input age here"))
        self.mf_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Gender:"), alignment=QtCore.Qt.AlignLeft)

        self.m_rb = QtWidgets.QRadioButton(QtWidgets.QApplication.translate("QtWidgets.QRadioButton", "Male"))
        self.f_rb = QtWidgets.QRadioButton(QtWidgets.QApplication.translate("QtWidgets.QRadioButton", "Female"))
        self.gna_rb = QtWidgets.QRadioButton(QtWidgets.QApplication.translate("QtWidgets.QRadioButton", "Unknown"))
        self.gna_rb.isChecked()

        self.interest_area_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Interests Area:"), alignment=QtCore.Qt.AlignLeft)
        self.interest_platform_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Interests platform:"), alignment=QtCore.Qt.AlignLeft)
        self.interest_platform_sel = QtWidgets.QComboBox()

        self.interest_platform_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Any"))
        self.interest_platform_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Amazon"))
        self.interest_platform_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Ebay"))
        self.interest_platform_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Etsy"))
        self.interest_platform_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Walmart"))
        self.interest_platform_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Wish"))
        self.interest_platform_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "AliExpress"))
        self.interest_platform_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Wayfair"))
        self.interest_platform_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Custom"))
        self.interest_platform_sel.currentTextChanged.connect(self.interestPlatformSel_changed)
        self.interest_main_category_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Interest Main Category:"), alignment=QtCore.Qt.AlignLeft)
        self.interest_main_category_sel = QtWidgets.QComboBox()
        self.interest_main_category_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Any"))
        self.interest_main_category_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Custom"))
        self.interest_main_category_sel.currentTextChanged.connect(self.interestMainCategorySel_changed)


        self.interest_sub_category1_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Interest Sub Category1:"), alignment=QtCore.Qt.AlignLeft)
        self.interest_sub_category1_sel = QtWidgets.QComboBox()
        self.interest_sub_category1_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Any"))
        self.interest_sub_category1_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Custom"))
        self.interest_sub_category1_sel.currentTextChanged.connect(self.interestSubCategory1Sel_changed)


        self.interest_sub_category2_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Interest Sub Category2:"), alignment=QtCore.Qt.AlignLeft)
        self.interest_sub_category2_sel = QtWidgets.QComboBox()
        self.interest_sub_category2_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Any"))
        self.interest_sub_category2_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Custom"))
        self.interest_sub_category2_sel.currentTextChanged.connect(self.interestSubCategory2Sel_changed)

        self.interest_sub_category3_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Interest Sub Category3:"), alignment=QtCore.Qt.AlignLeft)
        self.interest_sub_category3_sel = QtWidgets.QComboBox()
        self.interest_sub_category3_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Any"))
        self.interest_sub_category3_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Custom"))
        self.interest_sub_category3_sel.currentTextChanged.connect(self.interestSubCategory3Sel_changed)


        self.interest_sub_category4_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Interest Sub Category4:"), alignment=QtCore.Qt.AlignLeft)
        self.interest_sub_category4_sel = QtWidgets.QComboBox()
        self.interest_sub_category4_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Any"))
        self.interest_sub_category4_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Custom"))
        self.interest_sub_category4_sel.currentTextChanged.connect(self.interestSubCategory4Sel_changed)


        self.interest_sub_category5_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Interest Sub Category5:"), alignment=QtCore.Qt.AlignLeft)
        self.interest_sub_category5_sel = QtWidgets.QComboBox()
        self.interest_sub_category5_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Any"))
        self.interest_sub_category5_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Custom"))
        self.interest_sub_category5_sel.currentTextChanged.connect(self.interestSubCategory5Sel_changed)

        QtWidgets.QApplication.translate("QtWidgets.QLabel", "Interest Custom Main Sub Category1:")
        self.interest_custom_platform_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Interest Custom platform:"), alignment=QtCore.Qt.AlignLeft)
        self.interest_custom_platform_edit = QtWidgets.QLineEdit()
        self.interest_custom_main_category_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Interest Custom Main Category:"), alignment=QtCore.Qt.AlignLeft)
        self.interest_custom_main_category_edit = QtWidgets.QLineEdit()
        self.interest_custom_sub_category1_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Interest Custom Main Sub Category1:"), alignment=QtCore.Qt.AlignLeft)
        self.interest_custom_sub_category1_edit = QtWidgets.QLineEdit()
        self.interest_custom_sub_category2_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Interest Custom Main Sub Category2:"), alignment=QtCore.Qt.AlignLeft)
        self.interest_custom_sub_category2_edit = QtWidgets.QLineEdit()
        self.interest_custom_sub_category3_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Interest Custom Main Sub Category3:"), alignment=QtCore.Qt.AlignLeft)
        self.interest_custom_sub_category3_edit = QtWidgets.QLineEdit()
        self.interest_custom_sub_category4_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Interest Custom Main Sub Category4:"), alignment=QtCore.Qt.AlignLeft)
        self.interest_custom_sub_category4_edit = QtWidgets.QLineEdit()
        self.interest_custom_sub_category5_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Interest Custom Main Sub Category5:"), alignment=QtCore.Qt.AlignLeft)
        self.interest_custom_sub_category5_edit = QtWidgets.QLineEdit()

        self.role_platform_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Platform:"), alignment=QtCore.Qt.AlignLeft)
        self.role_platform_edit = QtWidgets.QLineEdit()
        self.role_platform_sel = QtWidgets.QComboBox()
        self.role_platform_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Amazon"))
        self.role_platform_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Ebay"))
        self.role_platform_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Etsy"))
        self.role_platform_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Walmart"))
        self.role_platform_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Wish"))
        self.role_platform_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "AliExpress"))
        self.role_platform_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Wayfair"))
        self.role_platform_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Custom"))
        self.role_platform_sel.currentTextChanged.connect(self.rolePlatformSel_changed)
        self.role_custom_platform_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Custom Platform:"), alignment=QtCore.Qt.AlignLeft)
        self.role_custom_platform_edit = QtWidgets.QLineEdit()
        self.role_level_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Level:"), alignment=QtCore.Qt.AlignLeft)
        self.role_level_edit = QtWidgets.QLineEdit()
        self.role_level_sel = QtWidgets.QComboBox()
        self.role_level_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Green"))
        QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Champ")
        self.role_level_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Experienced"))
        self.role_level_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Expert"))
        self.role_level_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Master"))
        self.role_level_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Champ"))
        self.role_level_sel.currentTextChanged.connect(self.roleLevelSel_changed)
        self.role_name_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Role:"), alignment=QtCore.Qt.AlignLeft)
        self.role_name_edit = QtWidgets.QLineEdit()
        self.role_name_sel = QtWidgets.QComboBox()
        self.role_name_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Buyer"))
        self.role_name_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Seller"))
        self.role_name_sel.currentTextChanged.connect(self.roleNameSel_changed)

        self.pubpflLine1Layout = QtWidgets.QHBoxLayout(self)
        self.pubpflLine1Layout.addWidget(self.tag_label)
        self.pubpflLine1Layout.addWidget(self.tag_edit)
        self.pubpflWidget_layout.addLayout(self.pubpflLine1Layout)

        self.pubpflLine2Layout = QtWidgets.QHBoxLayout(self)
        self.pubpflLine2Layout.addWidget(self.icon_label)
        self.pubpflLine2Layout.addWidget(self.icon_path_edit)
        self.pubpflLine2Layout.addWidget(self.icon_fs_button)
        self.pubpflWidget_layout.addLayout(self.pubpflLine2Layout)

        self.pubpflLine3Layout = QtWidgets.QHBoxLayout(self)
        self.pubpflLine3Layout.addWidget(self.pfn_label)
        self.pubpflLine3Layout.addWidget(self.pfn_edit)
        self.pubpflLine3Layout.addWidget(self.pln_label)
        self.pubpflLine3Layout.addWidget(self.pln_edit)
        self.pubpflWidget_layout.addLayout(self.pubpflLine3Layout)

        self.pubpflLine4Layout = QtWidgets.QHBoxLayout(self)
        self.pubpflLine4Layout.addWidget(self.pnn_label)
        self.pubpflLine4Layout.addWidget(self.pnn_edit)
        self.pubpflWidget_layout.addLayout(self.pubpflLine4Layout)

        self.pubpflLine5Layout = QtWidgets.QHBoxLayout(self)
        self.pubpflLine5Layout.addWidget(self.loccity_label)
        self.pubpflLine5Layout.addWidget(self.loccity_edit)
        self.pubpflLine5Layout.addWidget(self.locstate_label)
        self.pubpflLine5Layout.addWidget(self.locstate_edit)
        self.pubpflWidget_layout.addLayout(self.pubpflLine5Layout)

        self.pubpflLine6Layout = QtWidgets.QHBoxLayout(self)
        self.pubpflLine6Layout.addWidget(self.age_label)
        self.pubpflLine6Layout.addWidget(self.age_edit)
        self.pubpflWidget_layout.addLayout(self.pubpflLine6Layout)

        self.pubpflLine7Layout = QtWidgets.QHBoxLayout(self)
        self.pubpflLine7Layout.addWidget(self.mf_label)
        self.pubpflLine7Layout.addWidget(self.m_rb)
        self.pubpflLine7Layout.addWidget(self.f_rb)
        self.pubpflLine7Layout.addWidget(self.gna_rb)
        self.pubpflWidget_layout.addLayout(self.pubpflLine7Layout)

        self.pubpflLine7AALayout = QtWidgets.QHBoxLayout(self)
        self.pubpflLine7AALayout.addWidget(self.interest_area_label)
        self.pubpflWidget_layout.addLayout(self.pubpflLine7AALayout)

        self.pubpflLine7ALayout = QtWidgets.QHBoxLayout(self)
        self.pubpflLine7ALayout.addWidget(self.interest_platform_label)
        self.pubpflLine7ALayout.addWidget(self.interest_platform_sel)
        self.pubpflLine7ALayout.addWidget(self.interest_main_category_label)
        self.pubpflLine7ALayout.addWidget(self.interest_main_category_sel)
        self.pubpflLine7ALayout.addWidget(self.interest_sub_category1_label)
        self.pubpflLine7ALayout.addWidget(self.interest_sub_category1_sel)
        self.pubpflWidget_layout.addLayout(self.pubpflLine7ALayout)

        self.pubpflLine7BLayout = QtWidgets.QHBoxLayout(self)
        self.pubpflLine7BLayout.addWidget(self.interest_sub_category2_label)
        self.pubpflLine7BLayout.addWidget(self.interest_sub_category2_sel)
        self.pubpflLine7BLayout.addWidget(self.interest_sub_category3_label)
        self.pubpflLine7BLayout.addWidget(self.interest_sub_category3_sel)
        self.pubpflLine7BLayout.addWidget(self.interest_sub_category4_label)
        self.pubpflLine7BLayout.addWidget(self.interest_sub_category4_sel)
        self.pubpflLine7BLayout.addWidget(self.interest_sub_category5_label)
        self.pubpflLine7BLayout.addWidget(self.interest_sub_category5_sel)
        self.pubpflWidget_layout.addLayout(self.pubpflLine7BLayout)

        self.pubpflLine7DLayout = QtWidgets.QHBoxLayout(self)
        self.pubpflLine7DLayout.addWidget(self.interest_custom_platform_label)
        self.pubpflLine7DLayout.addWidget(self.interest_custom_platform_edit)
        self.pubpflLine7DLayout.addWidget(self.interest_custom_main_category_label)
        self.pubpflLine7DLayout.addWidget(self.interest_custom_main_category_edit)
        self.pubpflLine7DLayout.addWidget(self.interest_custom_sub_category1_label)
        self.pubpflLine7DLayout.addWidget(self.interest_custom_sub_category1_edit)
        self.pubpflWidget_layout.addLayout(self.pubpflLine7DLayout)

        self.pubpflLine7ELayout = QtWidgets.QHBoxLayout(self)
        self.pubpflLine7ELayout.addWidget(self.interest_custom_sub_category2_label)
        self.pubpflLine7ELayout.addWidget(self.interest_custom_sub_category2_edit)
        self.pubpflLine7ELayout.addWidget(self.interest_custom_sub_category3_label)
        self.pubpflLine7ELayout.addWidget(self.interest_custom_sub_category3_edit)
        self.pubpflLine7ELayout.addWidget(self.interest_custom_sub_category4_label)
        self.pubpflLine7ELayout.addWidget(self.interest_custom_sub_category4_edit)
        self.pubpflLine7ELayout.addWidget(self.interest_custom_sub_category5_label)
        self.pubpflLine7ELayout.addWidget(self.interest_custom_sub_category5_edit)
        self.pubpflWidget_layout.addLayout(self.pubpflLine7ELayout)

        self.hide_interest_custom_platform()
        self.hide_interest_custom_main_category()
        self.hide_interest_custom_sub_category1()
        self.hide_interest_custom_sub_category2()
        self.hide_interest_custom_sub_category3()
        self.hide_interest_custom_sub_category4()
        self.hide_interest_custom_sub_category5()
        self.pubpflWidget_layout.addWidget(self.interest_save_button)
        self.pubpflWidget_layout.addWidget(self.interestScrollArea)


        self.pubpflLine8Layout = QtWidgets.QHBoxLayout(self)
        self.pubpflLine8Layout.addWidget(self.role_platform_label)
        self.pubpflLine8Layout.addWidget(self.role_platform_sel)
        self.pubpflLine8Layout.addWidget(self.role_level_label)
        self.pubpflLine8Layout.addWidget(self.role_level_sel)
        self.pubpflLine8Layout.addWidget(self.role_name_label)
        self.pubpflLine8Layout.addWidget(self.role_name_sel)
        self.pubpflLine8Layout.addWidget(self.role_save_button)
        self.pubpflWidget_layout.addLayout(self.pubpflLine8Layout)

        self.pubpflLine9Layout = QtWidgets.QHBoxLayout(self)
        self.pubpflLine9Layout.addWidget(self.role_custom_platform_label)
        self.pubpflLine9Layout.addWidget(self.role_custom_platform_edit)

        self.pubpflWidget_layout.addLayout(self.pubpflLine9Layout)
        self.hide_role_custom_platform()

        self.pubpflWidget_layout.addWidget(self.roleScrollArea)

        # self.pubpflLine8Layout = QtWidgets.QHBoxLayout(self)
        # self.pubpflLine8Layout.addWidget(self.pnn_label)
        # self.pubpflLine8Layout.addWidget(self.pnn_edit)
        # self.pubpflWidget.layout.addLayout(self.pubpflLine8Layout)

        self.pubpflWidget.setLayout(self.pubpflWidget_layout)


        self.fn_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "First Name:"), alignment=QtCore.Qt.AlignLeft)
        self.fn_edit = QtWidgets.QLineEdit()

        self.fn_edit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "input First Name here"))
        self.ln_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Last Name:"), alignment=QtCore.Qt.AlignLeft)
        self.ln_edit = QtWidgets.QLineEdit()
        self.ln_edit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "input Last Name here"))
        self.bd_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Birthday:"), alignment=QtCore.Qt.AlignLeft)
        self.bd_edit = QtWidgets.QLineEdit()
        self.bd_edit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "input Birthday here in MM/DD/YYYY"))

        self.addr_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Address:"), alignment=QtCore.Qt.AlignLeft)
        self.shipaddr_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Shipping Address:"), alignment=QtCore.Qt.AlignLeft)
        self.addr_l1_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Address Line1:"), alignment=QtCore.Qt.AlignLeft)
        self.addr_l1_edit = QtWidgets.QLineEdit()

        self.addr_l2_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Address Line2:"), alignment=QtCore.Qt.AlignLeft)
        self.addr_l2_edit = QtWidgets.QLineEdit()

        self.addr_city_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "City:"), alignment=QtCore.Qt.AlignLeft)
        self.addr_city_edit = QtWidgets.QLineEdit()
        self.addr_state_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "State:"), alignment=QtCore.Qt.AlignLeft)
        self.addr_state_edit = QtWidgets.QLineEdit()
        self.addr_zip_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "ZIP:"), alignment=QtCore.Qt.AlignLeft)
        self.addr_zip_edit = QtWidgets.QLineEdit()

        self.shipaddr_same_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Shipping Address Same As Address?"), alignment=QtCore.Qt.AlignLeft)
        self.shipaddr_same_checkbox = QtWidgets.QCheckBox()
        self.shipaddr_same_checkbox.setCheckState(QtCore.Qt.CheckState.Unchecked)
        self.shipaddr_same_checkbox.stateChanged.connect(self.shipaddr_same_checkbox_toggled)

        self.shipaddr_l1_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Shipping Address Line1:"), alignment=QtCore.Qt.AlignLeft)
        self.shipaddr_l1_edit = QtWidgets.QLineEdit()

        self.shipaddr_l2_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Shipping Address Line2:"), alignment=QtCore.Qt.AlignLeft)
        self.shipaddr_l2_edit = QtWidgets.QLineEdit()

        self.shipaddr_city_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "City:"), alignment=QtCore.Qt.AlignLeft)
        self.shipaddr_city_edit = QtWidgets.QLineEdit()
        self.shipaddr_state_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "State:"), alignment=QtCore.Qt.AlignLeft)
        self.shipaddr_state_edit = QtWidgets.QLineEdit()
        self.shipaddr_zip_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Zip:"), alignment=QtCore.Qt.AlignLeft)
        self.shipaddr_zip_edit = QtWidgets.QLineEdit()

        self.phone_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Contact Phone:"), alignment=QtCore.Qt.AlignLeft)
        self.phone_edit = QtWidgets.QLineEdit()
        self.phone_edit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "(optional) contact phone number here"))
        self.em_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Contact Phone:"), alignment=QtCore.Qt.AlignLeft)
        self.em_edit = QtWidgets.QLineEdit()
        self.em_edit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "input email here"))
        self.empw_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Email Password:"), alignment=QtCore.Qt.AlignLeft)
        self.empw_edit = QtWidgets.QLineEdit()
        self.empw_edit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "input Email Password here"))
        self.backem_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Back Up Email:"), alignment=QtCore.Qt.AlignLeft)
        self.backem_edit = QtWidgets.QLineEdit()
        self.backem_edit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "(optional) back up email here"))
        self.acctpw_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "E-Business Account Password:"), alignment=QtCore.Qt.AlignLeft)
        self.acctpw_edit = QtWidgets.QLineEdit("")
        self.acctpw_edit.setPlaceholderText(QtWidgets.QApplication.translate("QtWidgets.QLineEdit", "(optional) E-Business Account Password here"))

        self.prvpflLine1Layout = QtWidgets.QHBoxLayout(self)
        self.prvpflLine1Layout.addWidget(self.fn_label)
        self.prvpflLine1Layout.addWidget(self.fn_edit)
        self.prvpflLine1Layout.addWidget(self.ln_label)
        self.prvpflLine1Layout.addWidget(self.ln_edit)
        self.prvpflWidget_layout.addLayout(self.prvpflLine1Layout)

        self.prvpflLine1ALayout = QtWidgets.QHBoxLayout(self)
        self.prvpflLine1ALayout.addWidget(self.bd_label)
        self.prvpflLine1ALayout.addWidget(self.bd_edit)
        self.prvpflWidget_layout.addLayout(self.prvpflLine1ALayout)

        self.prvpflLine1A1Layout = QtWidgets.QHBoxLayout(self)
        self.prvpflLine1A1Layout.addWidget(self.addr_label)
        self.prvpflWidget_layout.addLayout(self.prvpflLine1A1Layout)

        self.prvpflLine1BLayout = QtWidgets.QHBoxLayout(self)
        self.prvpflLine1BLayout.addWidget(self.addr_l1_label)
        self.prvpflLine1BLayout.addWidget(self.addr_l1_edit)
        self.prvpflWidget_layout.addLayout(self.prvpflLine1BLayout)

        self.prvpflLine1CLayout = QtWidgets.QHBoxLayout(self)
        self.prvpflLine1CLayout.addWidget(self.addr_l2_label)
        self.prvpflLine1CLayout.addWidget(self.addr_l2_edit)
        self.prvpflWidget_layout.addLayout(self.prvpflLine1CLayout)

        self.prvpflLine1DLayout = QtWidgets.QHBoxLayout(self)
        self.prvpflLine1DLayout.addWidget(self.addr_city_label)
        self.prvpflLine1DLayout.addWidget(self.addr_city_edit)
        self.prvpflLine1DLayout.addWidget(self.addr_state_label)
        self.prvpflLine1DLayout.addWidget(self.addr_state_edit)
        self.prvpflLine1DLayout.addWidget(self.addr_zip_label)
        self.prvpflLine1DLayout.addWidget(self.addr_zip_edit)
        self.prvpflWidget_layout.addLayout(self.prvpflLine1DLayout)

        self.prvpflLine1E1Layout = QtWidgets.QHBoxLayout(self)
        self.prvpflLine1E1Layout.addWidget(self.shipaddr_label)
        self.prvpflWidget_layout.addLayout(self.prvpflLine1E1Layout)

        self.prvpflLine1ELayout = QtWidgets.QHBoxLayout(self)
        self.prvpflLine1ELayout.addWidget(self.shipaddr_same_label)
        self.prvpflLine1ELayout.addWidget(self.shipaddr_same_checkbox)
        self.prvpflWidget_layout.addLayout(self.prvpflLine1ELayout)

        self.prvpflLine1FLayout = QtWidgets.QHBoxLayout(self)
        self.prvpflLine1FLayout.addWidget(self.shipaddr_l1_label)
        self.prvpflLine1FLayout.addWidget(self.shipaddr_l1_edit)
        self.prvpflWidget_layout.addLayout(self.prvpflLine1FLayout)

        self.prvpflLine1GLayout = QtWidgets.QHBoxLayout(self)
        self.prvpflLine1GLayout.addWidget(self.shipaddr_l2_label)
        self.prvpflLine1GLayout.addWidget(self.shipaddr_l2_edit)
        self.prvpflWidget_layout.addLayout(self.prvpflLine1GLayout)

        self.prvpflLine1HLayout = QtWidgets.QHBoxLayout(self)
        self.prvpflLine1HLayout.addWidget(self.shipaddr_city_label)
        self.prvpflLine1HLayout.addWidget(self.shipaddr_city_edit)
        self.prvpflLine1HLayout.addWidget(self.shipaddr_state_label)
        self.prvpflLine1HLayout.addWidget(self.shipaddr_state_edit)
        self.prvpflLine1HLayout.addWidget(self.shipaddr_zip_label)
        self.prvpflLine1HLayout.addWidget(self.shipaddr_zip_edit)
        self.prvpflWidget_layout.addLayout(self.prvpflLine1HLayout)


        self.prvpflLine2Layout = QtWidgets.QHBoxLayout(self)
        self.prvpflLine2Layout.addWidget(self.phone_label)
        self.prvpflLine2Layout.addWidget(self.phone_edit)
        self.prvpflWidget_layout.addLayout(self.prvpflLine2Layout)

        self.prvpflLine3Layout = QtWidgets.QHBoxLayout(self)
        self.prvpflLine3Layout.addWidget(self.em_label)
        self.prvpflLine3Layout.addWidget(self.em_edit)
        self.prvpflLine3Layout.addWidget(self.empw_label)
        self.prvpflLine3Layout.addWidget(self.empw_edit)
        self.prvpflWidget_layout.addLayout(self.prvpflLine3Layout)

        self.prvpflLine4Layout = QtWidgets.QHBoxLayout(self)
        self.prvpflLine4Layout.addWidget(self.backem_label)
        self.prvpflLine4Layout.addWidget(self.backem_edit)
        self.prvpflWidget_layout.addLayout(self.prvpflLine4Layout)

        self.prvpflLine5Layout = QtWidgets.QHBoxLayout(self)
        self.prvpflLine5Layout.addWidget(self.acctpw_label)
        self.prvpflLine5Layout.addWidget(self.acctpw_edit)
        self.prvpflWidget_layout.addLayout(self.prvpflLine5Layout)

        self.prvpflWidget.setLayout(self.prvpflWidget_layout)
        QtWidgets.QApplication.translate("QtWidgets.QLabel", "App Name:")
        self.browser_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "App Name:"), alignment=QtCore.Qt.AlignLeft)
        self.browser_sel = QtWidgets.QComboBox()
        self.browser_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "ADS"))

        self.browser_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Multi-Login"))
        self.browser_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "SuperBrowser"))
        self.browser_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Chrome"))
        self.browser_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Firefox"))
        self.browser_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Edge"))
        self.browser_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Edge"))

        self.os_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "OS Type:"), alignment=QtCore.Qt.AlignLeft)
        self.os_sel = QtWidgets.QComboBox()
        self.os_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Windows"))
        self.os_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "MacOS"))
        self.os_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "ChromeOS"))
        self.os_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Linux"))
        self.machine_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Machine Type:"), alignment=QtCore.Qt.AlignLeft)
        self.machine_sel = QtWidgets.QComboBox()
        self.machine_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Mac"))
        self.machine_sel.addItem(QtWidgets.QApplication.translate("QtWidgets.QComboBox", "Intel"))


        self.setngsLine1Layout = QtWidgets.QHBoxLayout(self)
        self.setngsLine1Layout.addWidget(self.machine_label)
        self.setngsLine1Layout.addWidget(self.machine_sel)
        self.setngsWidget_layout.addLayout(self.setngsLine1Layout)

        self.setngsLine2Layout = QtWidgets.QHBoxLayout(self)
        self.setngsLine2Layout.addWidget(self.os_label)
        self.setngsLine2Layout.addWidget(self.os_sel)
        self.setngsWidget_layout.addLayout(self.setngsLine2Layout)

        self.setngsLine3Layout = QtWidgets.QHBoxLayout(self)
        self.setngsLine3Layout.addWidget(self.browser_label)
        self.setngsLine3Layout.addWidget(self.browser_sel)
        self.setngsWidget_layout.addLayout(self.setngsLine3Layout)


        self.setngsWidget.setLayout(self.setngsWidget_layout)

        self.state_label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Enabled:"), alignment=QtCore.Qt.AlignLeft)
        self.state_en = QtWidgets.QCheckBox()
        self.state_en.setCheckState(QtCore.Qt.CheckState.Checked)


        self.statLine1Layout = QtWidgets.QHBoxLayout(self)
        self.statLine1Layout.addWidget(self.state_label)
        self.statLine1Layout.addWidget(self.state_en)
        self.statWidget_layout.addLayout(self.statLine1Layout)


        self.statWidget.setLayout(self.statWidget_layout)

        self.tabs.addTab(self.pubpflWidget, QtWidgets.QApplication.translate("QtWidgets.QTabWidget", "Pub Profile"))
        self.tabs.addTab(self.prvpflWidget, QtWidgets.QApplication.translate("QtWidgets.QTabWidget", "Private Profile"))
        self.tabs.addTab(self.setngsWidget, QtWidgets.QApplication.translate("QtWidgets.QTabWidget", "Settings"))
        self.tabs.addTab(self.statWidget, QtWidgets.QApplication.translate("QtWidgets.QTabWidget", "Status"))

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

    def hide_interest_custom_sub_category4(self):
        self.interest_custom_sub_category4_label.setVisible(False)
        self.interest_custom_sub_category4_edit.setVisible(False)

    def show_interest_custom_sub_category4(self):
        self.interest_custom_sub_category4_label.setVisible(True)
        self.interest_custom_sub_category4_edit.setVisible(True)

    def hide_interest_custom_sub_category5(self):
        self.interest_custom_sub_category5_label.setVisible(False)
        self.interest_custom_sub_category5_edit.setVisible(False)

    def show_interest_custom_sub_category5(self):
        self.interest_custom_sub_category5_label.setVisible(True)
        self.interest_custom_sub_category5_edit.setVisible(True)

    def saveRole(self):
        if self.role_platform_sel.currentText() == 'Custom':
            self.selected_role_platform = self.role_custom_platform_edit.text()

        self.newRole = ROLE(self.selected_role_platform, self.selected_role_level, self.selected_role_role)
        self.roleModel.appendRow(self.newRole)

        rw = ""
        lvl = ""
        for ri in range(self.roleModel.rowCount()):

            r = self.roleModel.item(ri)
            rw = rw + r.platform + ":" + r.role
            lvl = lvl + r.platform + ":" + r.role + ":" + r.level
            if ri != self.roleModel.rowCount():
                rw = rw + ","
                lvl = lvl + ","
        self.newBot.setRoles(rw)
        self.newBot.setLevels(lvl)


    def addInterest(self):
        if self.interest_platform_sel.currentText() == 'Custom':
            self.selected_interest_platform = self.interest_custom_platform_edit.text()

        if self.interest_main_category_sel.currentText() == 'Custom':
            self.selected_interest_main_category = self.interest_custom_main_category_edit.text()

        if self.interest_sub_category1_sel.currentText() == 'Custom':
            self.selected_interest_sub_category1 = self.interest_custom_sub_category1_edit.text()

        if self.interest_sub_category2_sel.currentText() == 'Custom':
            self.selected_interest_sub_category2 = self.interest_custom_sub_category2_edit.text()

        if self.interest_sub_category3_sel.currentText() == 'Custom':
            self.selected_interest_sub_category3 = self.interest_custom_sub_category3_edit.text()

        if self.interest_sub_category4_sel.currentText() == 'Custom':
            self.selected_interest_sub_category4 = self.interest_custom_sub_category4_edit.text()

        if self.interest_sub_category5_sel.currentText() == 'Custom':
            self.selected_interest_sub_category5 = self.interest_custom_sub_category5_edit.text()

        self.newInterest = INTEREST(self.selected_interest_platform, self.selected_interest_main_category, self.selected_interest_sub_category1, self.selected_interest_sub_category2, self.selected_interest_sub_category3, self.selected_interest_sub_category4, self.selected_interest_sub_category5)
        self.interestModel.appendRow(self.newInterest)

        interests = ""
        for ri in range(self.interestModel.rowCount()):
            r = self.interestModel.item(ri)
            interests = interests + r.name
            if ri != self.interestModel.rowCount():
                interests = interests + ","
        self.newBot.setInterests(interests)

    def setBot(self, bot):
        self.newBot = bot
        #now populate the GUI to reflect info in this bot.
        self.acctpw_edit.setText(bot.getAcctPw())
        self.age_edit.setText(str(bot.getAge()))
        self.backem_edit.setText(bot.getBackEm())
        self.loccity_edit.setText(bot.getLocation())
        self.em_edit.setText(bot.getEmail())
        self.empw_edit.setText(bot.getEmPW())
        self.fn_edit.setText(bot.getFn())
        self.ln_edit.setText(bot.getLn())
        #self.pln_edit.setText()
        #self.pfn_edit.setText()
        #self.pnn_edit.setText()
        self.phone_edit.setText(bot.getPhone())
        self.locstate_edit.setText(bot.getLocation())
        # self.icon_path_edit.setText(bot.getIconLink())
        #self.tag_edit.setText()
        if bot.getGender() == "Male":
            self.m_rb.setChecked(True)
        elif bot.getGender() == "Female":
            self.f_rb.setChecked(True)
        else:
            self.gna_rb.setChecked(True)
        self.os_sel.setCurrentText(bot.getOS())
        self.browser_sel.setCurrentText(bot.getBrowser())
        self.machine_sel.setCurrentText(bot.getMachine())

    def setOwner(self, owner):
        self.owner = owner
        self.newBot.setOwner(owner)

    def saveBot(self):
        print("saving bot....")
        # if this bot already exists, then, this is an update case, else this is a new bot creation case.
        #if self.mode == "new":
        #    self.newBot = EBBOT(self)

        self.newBot.pubProfile.setPseudoName(self.pnn_edit.text())
        self.newBot.pubProfile.setLoc(self.loccity_edit.text() + "|" + self.locstate_edit.text())
        if self.m_rb.isChecked():
            self.newBot.pubProfile.setPersonal(self.age_edit.text(), "Male")
        elif self.f_rb.isChecked():
            self.newBot.pubProfile.setPersonal(self.age_edit.text(), "Female")
        else:
            self.newBot.pubProfile.setPersonal(self.age_edit.text(), "NA")


        self.newBot.privateProfile.setName(self.fn_edit.text(), self.ln_edit.text())
        self.newBot.privateProfile.setAcct(self.em_edit.text(), self.empw_edit.text(), self.phone_edit.text(), self.backem_edit.text(), self.acctpw_edit.text())

        self.newBot.privateProfile.setBirthday(self.bd_edit.text())
        self.newBot.pubProfile.setAgeFromBirthday(self.newBot.privateProfile.getBirthday())

        self.newBot.settings.setComputer(self.os_sel.currentText(), self.machine_sel.currentText(), self.browser_sel.currentText())
        if self.mode == "new":
            print("adding new bot....")
            self.parent.addNewBot(self.newBot)
        elif self.mode == "update":
            print("update a bot....")
            self.parent.updateABot(self.newBot)

        self.newBot.privateProfile.setAddr(self.addr_l1_edit.text(), self.addr_l2_edit.text(), self.addr_city_edit.text(), self.addr_state_edit.text(), self.addr_zip_edit.text())
        self.newBot.privateProfile.setShippingAddr(self.shipaddr_l1_edit.text(), self.shipaddr_l2_edit.text(), self.shipaddr_city_edit.text(), self.shipaddr_state_edit.text(), self.shipaddr_zip_edit.text())

        self.close()
        # print(self.parent)

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
        if self.role_platform_sel.currentText() != 'Custom':
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


    def interestSubCategory4Sel_changed(self):
        if self.interest_sub_category4_sel.currentText() != 'Custom':
            self.hide_interest_custom_sub_category4()
            self.selected_interest_sub_category4 = self.interest_sub_category4_sel.currentText()
        else:
            self.show_interest_custom_sub_category4()
            self.selected_interest_sub_category4 = self.interest_custom_sub_category4_edit.text()

    def interestSubCategory5Sel_changed(self):
        if self.interest_sub_category5_sel.currentText() != 'Custom':
            self.hide_interest_custom_sub_category5()
            self.selected_interest_sub_category5 = self.interest_sub_category5_sel.currentText()
        else:
            self.show_interest_custom_sub_category5()
            self.selected_interest_sub_category5 = self.interest_custom_sub_category5_edit.text()


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

        # update sub cat 4
        if self.interest_sub_category4_sel.findText(sub_cat4) < 0:
            self.interest_sub_category4_sel.setCurrentText("Custom")
            self.interest_custom_sub_category4_edit.setText(sub_cat4)

        else:
            self.interest_sub_category4_sel.setCurrentText(sub_cat4)
            self.interest_custom_sub_category4_edit.setText("")

        # update sub cat 5
        if self.interest_sub_category5_sel.findText(sub_cat5) < 0:
            self.interest_sub_category5_sel.setCurrentText("Custom")
            self.interest_custom_sub_category5_edit.setText(sub_cat5)

        else:
            self.interest_sub_category5_sel.setCurrentText(sub_cat5)
            self.interest_custom_sub_category5_edit.setText("")


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
