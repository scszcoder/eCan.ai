import sys
import random

from PySide6.QtCore import QEvent, QStringListModel
from PySide6.QtGui import QStandardItemModel, QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QMainWindow, QTabWidget, QVBoxLayout, QLineEdit, \
    QCompleter, QComboBox, QScrollArea, QHBoxLayout, QRadioButton, QCheckBox, QFileDialog, QButtonGroup, QStyledItemDelegate, QFontComboBox
from ebbot import *
from locale import getdefaultlocale
from FlowLayout import *
from ebbot import *
from missions import *


class SkillListView(QListView):
    def __init__(self, parent):
        super(SkillListView, self).__init__()
        self.selected_row = None
        self.parent = parent
        self.homepath = parent.homepath

    def mousePressEvent(self, e):
        if e.type() == QEvent.MouseButtonPress:
            if e.button() == Qt.LeftButton:
                print("row:", self.indexAt(e.pos()).row())
                self.selected_row = self.indexAt(e.pos()).row()
                # self.parent.updateSelectedSkill(self.selected_row)



class MWORKSKILL(QStandardItem):
    def __init__(self, homepath, platform, app, applink, site, sitelink, action):
        super().__init__()
        self.platform = platform
        self.app = app
        self.applink = applink
        self.site = site
        self.homepath = homepath
        self.sitelink = sitelink
        self.action = action
        self.name = platform+"_"+app+"_"+site+"_"+action

        self.setText(self.name)
        self.icon = QIcon(homepath+'/resource/images/icons/skills-78.png')
        self.setIcon(self.icon)

    def getData(self):
        return self.platform, self.app, self.applink, self.site, self.sitelink, self.action


class CustomDelegate(QStyledItemDelegate):
    def __init__(self, parent):
        super(CustomDelegate, self).__init__(parent)
        self.parent = parent

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        # Check the item's text for customization
        item_text = index.data(Qt.DisplayRole)
        # if item_text == "5" or item_text == "11":
        if self.parent.checkIsMain(item_text):
            option.font.setBold(True)
            option.palette.setColor(QPalette.Text, QColor(0, 0, 255))  # Blue color

class MissionNewWin(QMainWindow):
    def __init__(self, parent):
        super(MissionNewWin, self).__init__(parent)

        self.text = QApplication.translate("QMainWindow", "new mission")
        self.parent = parent
        self.homepath = parent.homepath
        self.newMission = EBMISSION(parent)
        self.owner = None
        self.mode = "new"
        self.selected_skill_row = None
        self.selected_skill_item = None

        self.selected_mission_platform = "Windows"
        self.selected_mission_app = "Chrome"
        self.selected_mission_app_link = ""
        self.selected_mission_site = "Amazon"
        self.selected_mission_site_link = ""
        self.selected_skill_action = "Browse"

        self.mainWidget = QWidget()
        self.tabs = QTabWidget()
        self.pubAttrWidget = QWidget()
        self.prvAttrWidget = QWidget()
        self.actItemsWidget = QWidget()

        self.skillPanel = QFrame()
        self.skillPanelLayout = QVBoxLayout(self)

        self.skillListView = SkillListView(self)
        # self.skillListView.installEventFilter(self)


        self.skillModel = QStandardItemModel(self.skillListView)

        self.skillListView.setModel(self.skillModel)
        self.skillListView.setViewMode(QListView.ListMode)
        self.skillListView.setMovement(QListView.Snap)

        QApplication.translate("QLabel", "Skill Platform:")
        self.skillNameLabel = QLabel(QApplication.translate("QLabel", "Skill Name:"), alignment=Qt.AlignLeft)
        self.skillNameEdit = QLineEdit("")
        self.skillNameList = QStringListModel()
        self.skillNameCompleter = QCompleter(self.skillNameList, self)
        self.skillNameCompleter.setCaseSensitivity(Qt.CaseInsensitive)
        self.skillNameEdit.setCompleter(self.skillNameCompleter)

        self.missionPlatformLabel = QLabel(QApplication.translate("QLabel", "Mission Platform:"), alignment=Qt.AlignLeft)
        self.mission_platform_sel = QComboBox()
        for p in self.parent.getPLATFORMS():
            self.mission_platform_sel.addItem(QApplication.translate("QComboBox", p))
        self.mission_platform_sel.currentTextChanged.connect(self.missionPlatformSel_changed)


        self.missionAppLabel = QLabel(QApplication.translate("QLabel", "Mission App:"), alignment=Qt.AlignLeft)
        self.mission_app_sel = QComboBox()
        for app in self.parent.getAPPS():
            self.mission_app_sel.addItem(QApplication.translate("QComboBox", app))
        self.mission_app_sel.currentTextChanged.connect(self.missionAppSel_changed)

        QApplication.translate("QLabel", "Skill Site:")
        self.missionCustomAppNameLabel = QLabel(QApplication.translate("QLabel", "Custome App:"), alignment=Qt.AlignLeft)
        self.missionCustomAppNameEdit = QLineEdit("")

        self.missionCustomAppLinkLabel = QLabel(QApplication.translate("QLabel", "Custome App Path:"), alignment=Qt.AlignLeft)
        self.missionCustomAppLinkEdit = QLineEdit("")
        self.missionCustomAppLinkButton = QPushButton("...")
        self.missionCustomAppLinkButton.clicked.connect(self.chooseAppLinkDir)

        self.missionSiteLabel = QLabel(QApplication.translate("QLabel", "Mission Site:"), alignment=Qt.AlignLeft)
        self.mission_site_sel = QComboBox()
        for site in self.parent.getSITES():
            self.mission_site_sel.addItem(QApplication.translate("QComboBox", site))
        self.mission_site_sel.currentTextChanged.connect(self.missionSiteSel_changed)

        self.missionCustomSiteNameLabel = QLabel(QApplication.translate("QLabel", "Custom Site:"), alignment=Qt.AlignLeft)
        self.missionCustomSiteNameEdit = QLineEdit("")
        self.missionCustomSiteLinkLabel = QLabel(QApplication.translate("QLabel", "Custom Site Html:"), alignment=Qt.AlignLeft)
        self.missionCustomSiteLinkEdit = QLineEdit("")


        self.skillActionLabel = QLabel(QApplication.translate("QLabel", "Skill Action:"), alignment=Qt.AlignLeft)
        self.skill_action_sel = QComboBox()
        # self.skill_action_sel.setModel(self.parent.SkillManagerWin.skillModel)
        self.styleDelegate = CustomDelegate(self.parent)

        self.buildSkillSelList()
        self.skill_action_sel.setItemDelegate(self.styleDelegate)

        self.skill_action_sel.currentTextChanged.connect(self.skillActionSel_changed)


        self.skillCustomActionLabel = QLabel(QApplication.translate("QLabel", "Custom Action:"), alignment=Qt.AlignLeft)
        self.skillCustomActionEdit = QLineEdit("")

        self.skillScrollLabel = QLabel(QApplication.translate("QLabel", "Required Skills:"), alignment=Qt.AlignLeft)
        self.skillScroll = QScrollArea()
        self.skillScroll.setWidget(self.skillListView)
        self.skillScrollArea = QWidget()
        self.skillScrollLayout = QVBoxLayout(self)

        self.skillScrollLayout.addWidget(self.skillScrollLabel)
        self.skillScrollLayout.addWidget(self.skillScroll)
        self.skillScrollArea.setLayout(self.skillScrollLayout)

        self.skillButtonsArea = QWidget()
        self.skillButtonsLayout = QVBoxLayout(self)

        self.skill_add_button = QPushButton(QApplication.translate("QPushButton", "Add Skill"))
        self.skill_add_button.clicked.connect(self.addSkill)

        self.skill_remove_button = QPushButton(QApplication.translate("QPushButton", "Remove Skill"))
        self.skill_remove_button.clicked.connect(self.removeSkill)

        self.skillButtonsLayout.addWidget(self.skill_add_button)
        self.skillButtonsLayout.addWidget(self.skill_remove_button)
        self.skillButtonsArea.setLayout(self.skillButtonsLayout)

        self.skillArea = QWidget()
        self.skillAreaLayout = QHBoxLayout(self)
        self.skillAreaLayout.addWidget(self.skillScrollArea)
        self.skillAreaLayout.addWidget(self.skillButtonsArea)
        self.skillArea.setLayout(self.skillAreaLayout)


        self.save_button = QPushButton(QApplication.translate("QPushButton", "Save"))
        self.cancel_button = QPushButton(QApplication.translate("QPushButton", "Cancel"))

        self.action_confirm_cancel_button = QPushButton(QApplication.translate("QPushButton", "Cancel"))
        self.action_confirm_button = QPushButton(QApplication.translate("QPushButton", "Confirm"))
        self.action_confirm_ok_button = QPushButton(QApplication.translate("QPushButton", "OK"))

        self.layout = QVBoxLayout(self)
        self.bLayout = QHBoxLayout(self)
        self.bLayout.addWidget(self.cancel_button)
        self.bLayout.addWidget(self.save_button)

        self.pubAttrWidget.layout = QVBoxLayout(self)
        self.prvAttrWidget.layout = QVBoxLayout(self)
        self.actItemsWidget.layout = QVBoxLayout(self)

        self.ticket_label = QLabel(QApplication.translate("QLabel", "Ticket Number:"), alignment=Qt.AlignLeft)
        self.ticket_edit = QLineEdit()
        self.ticket_edit.setReadOnly(True)

        self.mid_label = QLabel(QApplication.translate("QLabel", "Mission ID:"), alignment=Qt.AlignLeft)
        self.mid_edit = QLineEdit()
        self.mid_edit.setReadOnly(True)

        self.mission_type_label = QLabel(QApplication.translate("QLabel", "Mission Type:"), alignment=Qt.AlignLeft)
        self.buy_rb = QRadioButton(QApplication.translate("QPushButton", "Buy Side"))
        self.buy_rb.toggled.connect(self.buy_rb_checked_state_changed)

        self.sell_rb = QRadioButton(QApplication.translate("QPushButton", "Sell Side"))

        self.mission_auto_assign_label = QLabel(QApplication.translate("QLabel", "Assignment Type:"), alignment=Qt.AlignLeft)
        self.manual_rb = QRadioButton(QApplication.translate("QPushButton", "Manual Assign(Bot and Schedule)"))
        self.auto_rb = QRadioButton(QApplication.translate("QPushButton", "Auto Assign(Bot and Schedule)"))


        self.bid_label = QLabel(QApplication.translate("QLabel", "Assigned Bot ID:"), alignment=Qt.AlignLeft)
        self.bid_edit = QLineEdit()
        self.ert_label = QLabel(QApplication.translate("QLabel", "Estimated Duration Time(Sec):"), alignment=Qt.AlignLeft)
        self.ert_edit = QLineEdit()
        self.est_label = QLabel(QApplication.translate("QLabel", "Estimated Start Time(hh:mm:ss):"), alignment=Qt.AlignLeft)
        self.est_edit = QLineEdit()

        self.buy_mission_type_label = QLabel(QApplication.translate("QLabel", "Buy Mission Type:"), alignment=Qt.AlignLeft)
        self.buy_mission_type_sel = QComboBox()

        for bt in self.parent.getBUYTYPES():
            self.buy_mission_type_sel.addItem(QApplication.translate("QComboBox", bt))

        self.sell_mission_type_label = QLabel(QApplication.translate("QLabel", "Sell Mission Type:"), alignment=Qt.AlignLeft)
        self.sell_mission_type_sel = QComboBox()

        for st in self.parent.getSELLTYPES():
            self.sell_mission_type_sel.addItem(QApplication.translate("QComboBox", st))

        self.repeat_label = QLabel(QApplication.translate("QLabel", "Repeat every:"), alignment=Qt.AlignLeft)
        self.repeat_edit = QLineEdit()
        self.repeat_edit.setPlaceholderText("1")

        # self.repeat_interval_label = QLabel(QApplication.translate("QLabel", " "), alignment=Qt.AlignLeft)
        # self.repeat_interval_sel = QComboBox()
        #
        # self.repeat_interval_sel.addItem(QApplication.translate("QComboBox", "Day(s)"))
        # self.repeat_interval_sel.addItem(QApplication.translate("QComboBox", "Week(s)"))
        # self.repeat_interval_sel.addItem(QApplication.translate("QComboBox", "Month(s)"))
        # self.repeat_interval_sel.addItem(QApplication.translate("QComboBox", "Year(s)"))
        # self.repeat_interval_sel.addItem(QApplication.translate("QComboBox", "Hour(s)"))
        # self.repeat_interval_sel.addItem(QApplication.translate("QComboBox", "Minute(s)"))

        self.search_kw_label = QLabel(QApplication.translate("QLabel", "Search Phrase:"), alignment=Qt.AlignLeft)
        self.search_kw_edit = QLineEdit()

        self.search_kw_edit.setPlaceholderText(QApplication.translate("QLineEdit", "Example: jump rope"))

        self.search_cat_label = QLabel(QApplication.translate("QLabel", "Search Category:"), alignment=Qt.AlignLeft)
        self.search_cat_edit = QLineEdit()

        self.search_cat_edit.setPlaceholderText(QApplication.translate("QLineEdit", "Example: Home&Garden->Garden Tools"))

        self.pseudo_store_label = QLabel(QApplication.translate("QLabel", "Pseudo Store:"), alignment=Qt.AlignLeft)
        self.pseudo_store_edit = QLineEdit()
        self.pseudo_store_edit.setPlaceholderText(QApplication.translate("QLineEdit", "Example: Jacks Shop, must be differrent from the actual store name."))

        self.pseudo_brand_label = QLabel(QApplication.translate("QLabel", "Pseudo Brand:"), alignment=Qt.AlignLeft)
        self.pseudo_brand_edit = QLineEdit()
        self.pseudo_brand_edit.setPlaceholderText(QApplication.translate("QLineEdit", "Example: abc, must be differrent from the actual brand name."))

        self.pseudo_asin_label = QLabel(QApplication.translate("QLabel", "Pseudo ASIN code:"), alignment=Qt.AlignLeft)
        self.pseudo_asin_edit = QLineEdit()
        self.pseudo_asin_edit.setPlaceholderText(QApplication.translate("QLineEdit", "Example: 123, must be differrent from the actual ASIN code/Serial code."))

        self.pubAttrLine1Layout = QHBoxLayout(self)
        self.pubAttrLine1Layout.addWidget(self.ticket_label)
        self.pubAttrLine1Layout.addWidget(self.ticket_edit)
        self.pubAttrLine1Layout.addWidget(self.mid_label)
        self.pubAttrLine1Layout.addWidget(self.mid_edit)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine1Layout)

        self.buy_sell_button_group = QButtonGroup()
        self.buy_sell_button_group.addButton(self.buy_rb)
        self.buy_sell_button_group.addButton(self.sell_rb)
        # self.buy_sell_button_group.setExclusive(False)


        self.pubAttrLine2Layout = QHBoxLayout(self)
        self.pubAttrLine2Layout.addWidget(self.mission_type_label)
        self.pubAttrLine2Layout.addWidget(self.buy_rb)
        self.pubAttrLine2Layout.addWidget(self.sell_rb)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine2Layout)

        self.auto_manual_button_group = QButtonGroup()
        self.auto_manual_button_group.addButton(self.manual_rb)
        self.auto_manual_button_group.addButton(self.auto_rb)

        self.pubAttrLine2ALayout = QHBoxLayout(self)
        self.pubAttrLine2ALayout.addWidget(self.mission_auto_assign_label)
        self.pubAttrLine2ALayout.addWidget(self.manual_rb)
        self.pubAttrLine2ALayout.addWidget(self.auto_rb)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine2ALayout)

        self.pubAttrLine2BLayout = QHBoxLayout(self)
        self.pubAttrLine2BLayout.addWidget(self.bid_label)
        self.pubAttrLine2BLayout.addWidget(self.bid_edit)
        self.pubAttrLine2BLayout.addWidget(self.ert_label)
        self.pubAttrLine2BLayout.addWidget(self.ert_edit)
        self.pubAttrLine2BLayout.addWidget(self.est_label)
        self.pubAttrLine2BLayout.addWidget(self.est_edit)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine2BLayout)


        self.pubAttrLine3Layout = QHBoxLayout(self)
        self.pubAttrLine3Layout.addWidget(self.repeat_label)
        self.pubAttrLine3Layout.addWidget(self.repeat_edit)
        # self.pubAttrLine3Layout.addWidget(self.repeat_interval_label)
        # self.pubAttrLine3Layout.addWidget(self.repeat_interval_sel)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine3Layout)

        self.pubAttrLine4Layout = QHBoxLayout(self)
        self.pubAttrLine4Layout.addWidget(self.search_kw_label)
        self.pubAttrLine4Layout.addWidget(self.search_kw_edit)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine4Layout)

        self.pubAttrLine5Layout = QHBoxLayout(self)
        self.pubAttrLine5Layout.addWidget(self.search_cat_label)
        self.pubAttrLine5Layout.addWidget(self.search_cat_edit)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine5Layout)


        self.pubAttrLine6Layout = QHBoxLayout(self)
        self.pubAttrLine6Layout.addWidget(self.pseudo_store_label)
        self.pubAttrLine6Layout.addWidget(self.pseudo_store_edit)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine6Layout)


        self.pubAttrLine7Layout = QHBoxLayout(self)
        self.pubAttrLine7Layout.addWidget(self.pseudo_brand_label)
        self.pubAttrLine7Layout.addWidget(self.pseudo_brand_edit)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine7Layout)


        self.pubAttrLine8Layout = QHBoxLayout(self)
        self.pubAttrLine8Layout.addWidget(self.pseudo_asin_label)
        self.pubAttrLine8Layout.addWidget(self.pseudo_asin_edit)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine8Layout)

        self.pubpflLine9Layout = QHBoxLayout(self)
        self.pubpflLine9Layout.addWidget(self.missionPlatformLabel)
        self.pubpflLine9Layout.addWidget(self.mission_platform_sel)
        self.pubpflLine9Layout.addWidget(self.missionAppLabel)
        self.pubpflLine9Layout.addWidget(self.mission_app_sel)
        self.pubpflLine9Layout.addWidget(self.missionSiteLabel)
        self.pubpflLine9Layout.addWidget(self.mission_site_sel)
        self.pubpflLine9Layout.addWidget(self.skillActionLabel)
        self.pubpflLine9Layout.addWidget(self.skill_action_sel)
        self.skillPanelLayout.addLayout(self.pubpflLine9Layout)


        self.pubpflLine11Layout = QHBoxLayout(self)
        self.pubpflLine11Layout.addWidget(self.missionCustomAppNameLabel)
        self.pubpflLine11Layout.addWidget(self.missionCustomAppNameEdit)
        self.pubpflLine11Layout.addWidget(self.missionCustomAppLinkLabel)
        self.pubpflLine11Layout.addWidget(self.missionCustomAppLinkEdit)
        self.skillPanelLayout.addLayout(self.pubpflLine11Layout)

        self.pubpflLine12Layout = QHBoxLayout(self)
        self.pubpflLine12Layout.addWidget(self.missionCustomSiteNameLabel)
        self.pubpflLine12Layout.addWidget(self.missionCustomSiteNameEdit)
        self.pubpflLine12Layout.addWidget(self.missionCustomSiteLinkLabel)
        self.pubpflLine12Layout.addWidget(self.missionCustomSiteLinkEdit)
        self.skillPanelLayout.addLayout(self.pubpflLine12Layout)

        self.pubpflLine13Layout = QHBoxLayout(self)
        self.pubpflLine13Layout.addWidget(self.skillCustomActionLabel)
        self.pubpflLine13Layout.addWidget(self.skillCustomActionEdit)
        self.skillPanelLayout.addLayout(self.pubpflLine13Layout)

        self.hide_mission_custom_app()
        self.hide_mission_custom_site()
        self.hide_skill_custom_action()

        self.skillPanelLayout.addWidget(self.skillArea)
        self.skillPanel.setLayout(self.skillPanelLayout)

        self.skillPanel.setFrameStyle(QFrame.Panel|QFrame.Raised)

        self.pubAttrWidget.layout.addWidget(self.skillPanel)

        self.skillPanel = QFrame()
        self.skillPanelLayout = QVBoxLayout(self)




        self.pubAttrWidget.setLayout(self.pubAttrWidget.layout)

        self.cus_fn_label = QLabel(QApplication.translate("QLabel", "Customer First Name:"), alignment=Qt.AlignLeft)
        self.cus_fn_edit = QLineEdit()
        self.cus_fn_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input Customer First Name here"))

        self.cus_ln_label = QLabel(QApplication.translate("QLabel", "Customer Last Name:"), alignment=Qt.AlignLeft)
        self.cus_ln_edit = QLineEdit()
        self.cus_ln_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input Customer Last Name here"))

        self.cus_nn_label = QLabel(QApplication.translate("QLabel", "Customer Nick Name:"), alignment=Qt.AlignLeft)
        self.cus_nn_edit = QLineEdit()
        self.cus_nn_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input Customer Nick Name here"))

        self.cus_id_label = QLabel(QApplication.translate("QLabel", "Customer ID:"), alignment=Qt.AlignLeft)
        self.cus_id_edit = QLineEdit()
        self.cus_id_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input Customer ID here"))

        self.cus_sm_type_label = QLabel(QApplication.translate("QLabel", "Customer Messenging Type:"), alignment=Qt.AlignLeft)
        self.cus_sm_type_sel = QComboBox()

        self.cus_sm_type_sel.addItem(QApplication.translate("QComboBox", "QQ"))
        self.cus_sm_type_sel.addItem(QApplication.translate("QComboBox", "WeChat"))
        self.cus_sm_type_sel.addItem(QApplication.translate("QComboBox", "Telegram"))
        self.cus_sm_type_sel.addItem(QApplication.translate("QComboBox", "WhatsApp"))
        self.cus_sm_type_sel.addItem(QApplication.translate("QComboBox", "Messenger"))
        self.cus_sm_type_sel.addItem(QApplication.translate("QComboBox", "Other"))

        self.cus_sm_id_label = QLabel(QApplication.translate("QLabel", "Customer Messenger ID:"), alignment=Qt.AlignLeft)
        self.cus_sm_id_edit = QLineEdit()
        self.cus_sm_id_edit.setPlaceholderText(QApplication.translate("QLineEdit", "Customer Messenger ID here"))

        self.cus_alt_sm_type_label = QLabel(QApplication.translate("QLabel", "Customer Messenging Type:"), alignment=Qt.AlignLeft)
        self.cus_alt_sm_type_sel = QComboBox()
        for sm in self.parent.getSMPLATFORMS():
            self.cus_alt_sm_type_sel.addItem(QApplication.translate("QComboBox", sm))

        self.cus_alt_sm_id_label = QLabel(QApplication.translate("QLabel", "Customer Messenger ID:"), alignment=Qt.AlignLeft)
        self.cus_alt_sm_id_edit = QLineEdit()

        self.cus_alt_sm_id_edit.setPlaceholderText(QApplication.translate("QLineEdit", "Customer Messenger ID here"))
        self.cus_email_label = QLabel(QApplication.translate("QLabel", "Customer Email:"), alignment=Qt.AlignLeft)
        self.cus_email_edit = QLineEdit()
        self.cus_email_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input Customer Email"))
        self.cus_phone_label = QLabel(QApplication.translate("QLabel", "Customer Contact Phone:"), alignment=Qt.AlignLeft)
        self.cus_phone_edit = QLineEdit()
        self.cus_phone_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input Customer Contact Phone here"))
        self.asin_label = QLabel(QApplication.translate("QLabel", "Product ASIN/ID:"), alignment=Qt.AlignLeft)
        self.asin_edit = QLineEdit()
        self.asin_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input product ASIN/ID here"))
        self.title_label = QLabel(QApplication.translate("QLabel", "Product Title:"), alignment=Qt.AlignLeft)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input product title here"))
        self.seller_label = QLabel(QApplication.translate("QLabel", "Product Seller:"), alignment=Qt.AlignLeft)
        self.seller_edit = QLineEdit()
        self.seller_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input seller here"))
        self.rating_label = QLabel(QApplication.translate("QLabel", "Rating:"), alignment=Qt.AlignLeft)
        self.rating_edit = QLineEdit()
        self.rating_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input rating here"))

        self.feedbacks_label = QLabel(QApplication.translate("QLabel", "# of feedbacks:"), alignment=Qt.AlignLeft)
        self.feedbacks_edit = QLineEdit()
        self.feedbacks_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input # feedbacks here"))

        self.price_label = QLabel(QApplication.translate("QLabel", "Selling Price:"), alignment=Qt.AlignLeft)
        self.price_edit = QLineEdit()
        self.price_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input selling price here, ex. 12.99"))

        self.product_image_label = QLabel(QApplication.translate("QLabel", "Top Image:"), alignment=Qt.AlignLeft)
        self.product_image_edit = QLineEdit()
        self.product_image_edit.setPlaceholderText(QApplication.translate("QLineEdit", "input image path here"))

        self.prvAttrLine1Layout = QHBoxLayout(self)
        self.prvAttrLine1Layout.addWidget(self.cus_id_label)
        self.prvAttrLine1Layout.addWidget(self.cus_id_edit)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine1Layout)

        self.prvAttrLine2Layout = QHBoxLayout(self)
        self.prvAttrLine2Layout.addWidget(self.cus_sm_id_label)
        self.prvAttrLine2Layout.addWidget(self.cus_sm_id_edit)
        self.prvAttrLine2Layout.addWidget(self.cus_alt_sm_type_label)
        self.prvAttrLine2Layout.addWidget(self.cus_alt_sm_type_sel)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine2Layout)

        self.prvAttrLine3Layout = QHBoxLayout(self)
        self.prvAttrLine3Layout.addWidget(self.asin_label)
        self.prvAttrLine3Layout.addWidget(self.asin_edit)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine3Layout)

        self.prvAttrLine4Layout = QHBoxLayout(self)
        self.prvAttrLine4Layout.addWidget(self.title_label)
        self.prvAttrLine4Layout.addWidget(self.title_edit)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine4Layout)

        self.prvAttrLine5Layout = QHBoxLayout(self)
        self.prvAttrLine5Layout.addWidget(self.seller_label)
        self.prvAttrLine5Layout.addWidget(self.seller_edit)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine5Layout)

        self.prvAttrLine6Layout = QHBoxLayout(self)
        self.prvAttrLine6Layout.addWidget(self.rating_label)
        self.prvAttrLine6Layout.addWidget(self.rating_edit)
        self.prvAttrLine6Layout.addWidget(self.feedbacks_label)
        self.prvAttrLine6Layout.addWidget(self.feedbacks_edit)
        self.prvAttrLine6Layout.addWidget(self.price_label)
        self.prvAttrLine6Layout.addWidget(self.price_edit)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine6Layout)

        self.prvAttrLine7Layout = QHBoxLayout(self)
        self.prvAttrLine7Layout.addWidget(self.product_image_label)
        self.prvAttrLine7Layout.addWidget(self.product_image_edit)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine7Layout)

        self.prvAttrLine8Layout = QHBoxLayout(self)
        self.prvAttrLine8Layout.addWidget(self.buy_mission_type_label)
        self.prvAttrLine8Layout.addWidget(self.buy_mission_type_sel)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine8Layout)

        self.prvAttrLine9Layout = QHBoxLayout(self)
        self.prvAttrLine9Layout.addWidget(self.sell_mission_type_label)
        self.prvAttrLine9Layout.addWidget(self.sell_mission_type_sel)
        self.prvAttrWidget.layout.addLayout(self.prvAttrLine9Layout)


        self.prvAttrWidget.setLayout(self.prvAttrWidget.layout)

        self.bought_label = QLabel(QApplication.translate("QLabel", "Item Bought:"), alignment=Qt.AlignLeft)
        self.bought_cb = QCheckBox()
        self.received_label = QLabel(QApplication.translate("QLabel", "Item Received:"), alignment=Qt.AlignLeft)
        self.received_cb = QCheckBox()
        self.fb_rated_label = QLabel(QApplication.translate("QLabel", "Feedback Rated:"), alignment=Qt.AlignLeft)
        self.fb_rated_cb = QCheckBox()
        self.fb_reviewed_label = QLabel(QApplication.translate("QLabel", "Feedback Reviewed:"), alignment=Qt.AlignLeft)
        self.fb_reviewed_cb = QCheckBox()


        self.actItemsLine1Layout = QHBoxLayout(self)
        self.actItemsLine1Layout.addWidget(self.bought_label)
        self.actItemsLine1Layout.addWidget(self.bought_cb)
        self.actItemsWidget.layout.addLayout(self.actItemsLine1Layout)

        self.actItemsLine2Layout = QHBoxLayout(self)
        self.actItemsLine2Layout.addWidget(self.received_label)
        self.actItemsLine2Layout.addWidget(self.received_cb)
        self.actItemsWidget.layout.addLayout(self.actItemsLine2Layout)

        self.actItemsLine3Layout = QHBoxLayout(self)
        self.actItemsLine3Layout.addWidget(self.fb_rated_label)
        self.actItemsLine3Layout.addWidget(self.fb_rated_cb)
        self.actItemsWidget.layout.addLayout(self.actItemsLine3Layout)

        self.actItemsLine4Layout = QHBoxLayout(self)
        self.actItemsLine4Layout.addWidget(self.fb_reviewed_label)
        self.actItemsLine4Layout.addWidget(self.fb_reviewed_cb)
        self.actItemsWidget.layout.addLayout(self.actItemsLine4Layout)

        self.actItemsWidget.setLayout(self.actItemsWidget.layout)

        self.tabs.addTab(self.pubAttrWidget, QApplication.translate("QTabWidget", "Pub Attributes"))
        self.tabs.addTab(self.prvAttrWidget, QApplication.translate("QTabWidget", "Private Attributes"))
        self.tabs.addTab(self.actItemsWidget, QApplication.translate("QTabWidget", "Action Items"))

        self.layout.addWidget(self.tabs)
        self.layout.addLayout(self.bLayout)

        # self.layout.addWidget(self.text)
        # self.layout.addRow(self.browser_path_label, self.browser_path_line_edit);
        # self.layout.addRow(self.date_time_label, self.date_time_start)
        # self.layout.addRow(self.task_settings_button)
        # self.layout.addRow(self.cancel_button, self.save_button)

        self.save_button.clicked.connect(self.saveMission)
        self.cancel_button.clicked.connect(self.close)

        self.mainWidget.setLayout(self.layout)
        self.setCentralWidget(self.mainWidget)

        self.buy_rb.setChecked(True)



    def setMode(self, mode):
        self.mode = mode
        if self.mode == "new":
            self.setWindowTitle('Adding a new mission')
        elif self.mode == "update":
            self.setWindowTitle('Updating a mission')

    def saveMission(self):
        print("saving bot....")
        # if this bot already exists, then, this is an update case, else this is a new bot creation case.

        if self.manual_rb.isChecked():
            if int(self.bid_edit.text()) != self.newMission.getBid():
                self.newMission.setBid(int(self.bid_edit.text()))
                self.newMission.setEstimatedStartTime(self.est_edit.text())
                self.newMission.setEstimatedRunTime(self.ert_edit.text())

        if self.repeat_edit.text().isnumeric():
            self.newMission.setRetry(int(self.repeat_edit.text()))

        if self.buy_rb.isChecked():
            if self.auto_rb.isChecked():
                self.newMission.pubAttributes.setType("auto", "buy")
            else:
                self.newMission.pubAttributes.setType("manual", "buy")
        elif self.sell_rb.isChecked():
            if self.auto_rb.isChecked():
                self.newMission.pubAttributes.setType("auto", "sell")
            else:
                self.newMission.pubAttributes.setType("manual", "sell")


        self.newMission.setBuyType(self.buy_mission_type_sel.currentText())
        self.newMission.setSellType(self.sell_mission_type_sel.currentText())

        self.newMission.privateAttributes.setItem(self.asin_edit.text(), self.seller_edit.text(), self.title_edit.text(), self.product_image_edit.text(), self.rating_edit.text(), self.feedbacks_edit.text(), self.price_edit.text())

        self.newMission.setCustomerID(self.cus_email_edit.text())
        self.newMission.setCustomerSMID(self.cus_sm_id_edit.text())
        self.newMission.setCustomerSMPlatform(self.cus_alt_sm_type_sel.currentText())

        if self.fb_reviewed_cb.isChecked():
            self.newMission.setStatus("reviewed")
        elif self.fb_rated_cb.isChecked():
            self.newMission.setStatus("rated")
        elif self.received_cb.isChecked():
            self.newMission.setStatus("received")
        elif self.bought_cb.isChecked():
            self.newMission.setStatus("bought")


        self.newMission.pubAttributes.setSearch(self.search_kw_edit.text(), self.search_cat_edit.text())

        self.newMission.setPseudoStore(self.pseudo_store_edit.text())
        self.newMission.setPseudoBrand(self.pseudo_brand_edit.text())
        self.newMission.setPseudoASIN(self.pseudo_asin_edit.text())

        platform_text = self.mission_platform_sel.currentText()
        platform_sh = self.parent.translatePlatform(platform_text)
        self.newMission.setPlatform(platform_text)

        if self.mission_app_sel.currentText() == 'Custom':
            app_text = self.missionCustomAppNameEdit.text()
        else:
            app_text = self.mission_app_sel.currentText()

        app_sh = app_text
        self.newMission.setApp(app_text)

        if self.mission_site_sel.currentText() == 'Custom':
            site_text = self.missionCustomSiteNameEdit.text()
        else:
            site_text = self.mission_site_sel.currentText()

        site_sh = self.parent.translateSiteName(site_text)
        self.newMission.setSite(site_text)

        print("Setting CusPAS:", platform_sh+","+app_sh+","+site_sh)
        self.newMission.setCusPAS(platform_sh+","+app_sh+","+site_sh)
        self.fillSkills()

        # public: type,


        if self.mode == "new":
            print("adding new mission....")
            self.parent.addNewMission(self.newMission)
        elif self.mode == "update":
            print("update a mission....")
            self.parent.updateAMission(self.newMission)

        self.close()


    def loadSkills(self, mission):
        skp_options = ['win', 'mac', 'linux']
        skapp_options = ['chrome', 'edge', 'firefox', 'safari', 'ads', 'multilogin']
        sksite_options = ['amz', 'etsy', 'ebay']
        all_skids = mission.getSkills().split(",")

        for skidw in all_skids:
            skid = skidw.strip()
            this_skill = next((x for x in self.parent.skills if x.getSkid() == skid), None)

            if this_skill:
                self.skillModel.appendRow(this_skill)

        self.selected_skill_row = 0
        self.selected_skill_item = self.skillModel.item(self.selected_skill_row)


    def fillSkills(self):
        sk_word = ""
        for i in range(self.skillModel.rowCount()):
            self.selected_skill_item = self.skillModel.item(i)
            skid = self.selected_skill_item.getSkid()
            sk_word = sk_word + "," + str(skid)

        print("skills>>>>>", sk_word)

        self.newMission.setSkills(sk_word)

    def selFile(self):
        # File actions
        fdir = self.fsel.getExistingDirectory()
        print(fdir)
        return fdir

    def setOwner(self, owner):
        self.owner = owner
        self.newMission.setOwner(owner)

    def setMission(self, mission):
        self.newMission = mission
        print("setting mission id:", str(self.newMission.getMid()))
        self.mid_edit.setText(str(self.newMission.getMid()))
        self.ticket_edit.setText(str(self.newMission.getTicket()))
        self.bid_edit.setText(str(self.newMission.getBid()))
        self.est_edit.setText(str(self.newMission.getEstimatedStartTime()))
        self.ert_edit.setText(str(self.newMission.getEstimatedRunTime()))

        self.repeat_edit.setText(str(self.newMission.getRetry()))

        if self.newMission.getMtype() == "buy":
            self.buy_rb.setChecked(True)
        else:
            self.sell_rb.setChecked(True)

        if self.newMission.getAssignmentType() == "auto":
            self.auto_rb.setChecked(True)
        else:
            self.manual_rb.setChecked(True)

        if self.newMission.getBuyType() in self.parent.getBUYTYPES():
            self.buy_mission_type_sel.setCurrentText(self.newMission.getBuyType())
        else:
            self.buy_mission_type_sel.setCurrentText("buy")

        if self.newMission.getSellType() in self.parent.getSELLTYPES():
            self.sell_mission_type_sel.setCurrentText(self.newMission.getSellType())
        else:
            self.sell_mission_type_sel.setCurrentText("sell")

        self.asin_edit.setText(self.newMission.getASIN())
        self.seller_edit.setText(self.newMission.getStore())
        self.title_edit.setText(self.newMission.getTitle())
        self.product_image_edit.setText(self.newMission.getImagePath())
        self.rating_edit.setText(str(self.newMission.getRating()))
        self.feedbacks_edit.setText(str(self.newMission.getFeedbacks()))
        self.price_edit.setText(str(self.newMission.getPrice()))
        self.cus_email_edit.setText(self.newMission.getCustomerID())
        self.cus_sm_id_edit.setText(self.newMission.getCustomerSMID())

        if self.newMission.getCustomerSMPlatform() in self.parent.getSMPLATFORMS():
            self.cus_alt_sm_type_sel.setCurrentText(self.newMission.getCustomerSMPlatform())
        else:
            self.cus_alt_sm_type_sel.setCurrentText("Custom")

        if self.newMission.getStatus() == "reviewed":
            self.fb_reviewed_cb.setChecked(True)
        elif self.newMission.getStatus() == "rated":
            self.fb_rated_cb.setChecked(True)
        elif self.newMission.getStatus() == "received":
            self.received_cb.setChecked(True)
        elif self.newMission.getStatus() == "bought":
            self.bought_cb.setChecked(True)

        self.search_kw_edit.setText(self.newMission.getSearchKW())
        self.search_cat_edit.setText(self.newMission.getSearchCat())
        self.pseudo_store_edit.setText(self.newMission.getPseudoStore())
        self.pseudo_brand_edit.setText(self.newMission.getPseudoBrand())
        self.pseudo_asin_edit.setText(self.newMission.getPseudoASIN())

        self.mission_platform_sel.setCurrentText(self.newMission.getPlatform())
        if self.newMission.getApp() in self.parent.getAPPS():
            self.mission_app_sel.setCurrentText(self.newMission.getApp())
        else:
            self.mission_app_sel.setCurrentText('Custom')
            self.missionCustomAppNameEdit.setText(self.newMission.getApp())
            self.missionCustomAppLinkEdit.setText(self.newMission.getAppExe())

        if self.newMission.getSite() in self.parent.getSITES():
            self.mission_site_sel.setCurrentText(self.newMission.getSite())
        else:
            self.mission_site_sel.setCurrentText('Custom')
            self.missionCustomAppNameEdit.setText(self.newMission.getSite())
            self.missionCustomAppLinkEdit.setText(self.newMission.getSiteH())

        self.loadSkills(mission)


    def missionPlatformSel_changed(self):
        self.missionCustomAppLinkEdit = self.mission_platform_sel.currentText()


    def missionAppSel_changed(self):
        print("app changed....")
        if self.mission_app_sel.currentText() != 'Custom':
            self.hide_mission_custom_app()
            self.selected_mission_app = self.mission_app_sel.currentText()
            self.selected_mission_app_link = ""

        else:
            self.show_mission_custom_app()
            self.selected_mission_app = self.missionCustomAppNameEdit.text()
            self.selected_mission_app_link = self.missionCustomAppLinkEdit.text()

    def missionSiteSel_changed(self):
        if self.mission_site_sel.currentText() != 'Custom':
            self.hide_mission_custom_site()
            self.selected_mission_site = self.mission_site_sel.currentText()
            self.selected_mission_site_link = ""
        else:
            self.show_mission_custom_site()
            self.selected_mission_site = self.missionCustomSiteNameEdit.text()
            self.selected_mission_site_link = self.missionCustomSiteLinkEdit.text()

    def skillActionSel_changed(self):
        if self.skill_action_sel.currentText() != 'Custom':
            self.hide_skill_custom_action()
            self.selected_skill_action = self.skill_action_sel.currentText()
        else:
            self.show_skill_custom_action()
            self.selected_skill_action = self.skillCustomActionEdit.text()


    def hide_mission_custom_app(self):
        self.missionCustomAppNameLabel.setVisible(False)
        self.missionCustomAppNameEdit.setVisible(False)
        self.missionCustomAppLinkLabel.setVisible(False)
        self.missionCustomAppLinkEdit.setVisible(False)

    def show_mission_custom_app(self):
        self.missionCustomAppNameLabel.setVisible(True)
        self.missionCustomAppNameEdit.setVisible(True)
        self.missionCustomAppLinkLabel.setVisible(True)
        self.missionCustomAppLinkEdit.setVisible(True)


    def hide_mission_custom_site(self):
        self.missionCustomSiteNameLabel.setVisible(False)
        self.missionCustomSiteNameEdit.setVisible(False)
        self.missionCustomSiteLinkLabel.setVisible(False)
        self.missionCustomSiteLinkEdit.setVisible(False)


    def show_mission_custom_site(self):
        self.missionCustomSiteNameLabel.setVisible(True)
        self.missionCustomSiteNameEdit.setVisible(True)
        self.missionCustomSiteLinkLabel.setVisible(True)
        self.missionCustomSiteLinkEdit.setVisible(True)

    def hide_skill_custom_action(self):
        self.skillCustomActionLabel.setVisible(False)
        self.skillCustomActionEdit.setVisible(False)

    def show_skill_custom_action(self):
        self.skillCustomActionLabel.setVisible(True)
        self.skillCustomActionEdit.setVisible(True)

    def chooseAppLinkDir(self):
        self.missionCustomAppLinkEdit.setText(str(QFileDialog.getExistingDirectory(self, "Select Directory")))
        self.selected_skill_app_link = self.missionCustomAppLinkEdit.text()

    def addSkill(self):
        if self.skill_app_sel.currentText() == 'Custom':
            self.selected_skill_app = self.skillCustomAppNameEdit.text()
            self.selected_skill_app_link = self.skillCustomAppLinkEdit.text()

        if self.skill_site_sel.currentText() == 'Custom':
            self.selected_skill_site = self.skillCustomSiteNameEdit.text()
            self.selected_skill_site_link = self.skillCustomSiteLinkEdit.text()

        sk_words = self.skill_action_sel.currentText().split("_")
        sk_platform = sk_words[0]
        sk_app = sk_words[1]
        sk_site = sk_words[2]
        sk_page = sk_words[3]
        sk_name = "_".join(sk_words[4:])
        this_skill = next((x for x in self.parent.skills if x.getPlatform() == sk_platform and x.getApp() == sk_app and x.getSite() == sk_site and x.getPage() == sk_page and x.getName() == sk_name), None)

        self.skillModel.appendRow(this_skill)

        # automatically add dependency skills to the list as well
        sk_dep = this_skill.getDependencies()
        if len(sk_dep) > 0:
            for skid in sk_dep:
                dep_skill = next((x for x in self.parent.skills if x.getSkid() == skid ), None)
                self.skillModel.appendRow(dep_skill)


    def removeSkill(self):
        # a bit complicated here, need to make sure if the skill is a dependent skill, then it's not removable.
        # if it's a main skill, then removing it will remove all of its dependency , and even more tricky is
        # if one of this main skill's dependency is also another main skill's dependency, then this item is also
        # not removable.
        rows_to_be_removed = [self.skillListView.selected_row]
        all_mission_skills = [self.skillModel.item(row) for row in range(self.skillModel.rowCount())]
        other_main_skills = list(filter(lambda sk: sk.getIsMain() and sk.getSkid() != self.selected_skill_item.getSkid(), all_mission_skills))

        if self.selected_skill_item.getIsMain():
            # first go thru its dependencies and check whether a skill is
            deps = self.selected_skill_item.getDependencies()
            for dep in deps:
                dependent_to_others = False
                for other in other_main_skills:
                    if dep in other.getDependencies():
                        dependent_to_others = True
                        break

                if not dependent_to_others:
                    dep_row = next((i for i, item in enumerate(all_mission_skills) if item.getSkid() == dep), -1)
                    rows_to_be_removed.append(dep_row)
                    break

            sorted_rows_to_be_removed = rows_to_be_removed.sort(reverse=True)
            # finally remove items from bottom to top.
            for row in sorted_rows_to_be_removed:
                self.skillModel.removeRow(row)


    def _createSkillDeleteAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Delete"))
        return new_action

    def _createSkillUpdateAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Update"))
        return new_action


    def eventFilter(self, source, event):
        if event.type() == QEvent.ContextMenu and source is self.skillListView:
            #print("bot RC menu....")
            self.popMenu = QMenu(self)
            self.skillUpdateAction = self._createSkillUpdateAction()
            self.skillDeleteAction = self._createSkillDeleteAction()

            self.popMenu.addAction(self.skillUpdateAction)
            self.popMenu.addSeparator()
            self.popMenu.addAction(self.skillDeleteAction)

            selected_act = self.popMenu.exec_(event.globalPos())
            if selected_act:
                self.selected_skill_row = source.indexAt(event.pos()).row()
                self.selected_skill_item = self.skillModel.item(self.selected_skill_row)
                if selected_act == self.skillDeleteAction:
                    self.removeSkill()
                elif selected_act == self.skillUpdateAction:
                    self.updateSelectedSkill(self.selected_skill_row)
            return True

            ##print(event.)

        # else:
        #     print("unknwn.... RC menu....", source, " EVENT: ", event)
        return super().eventFilter(source, event)


    def updateSelectedSkill(self, row):
        self.selected_skill_row = row
        self.selected_skill_item = self.skillModel.item(self.selected_skill_row)
        if self.selected_skill_item:
            platform, app, applink, site, sitelink, action = self.selected_skill_item.getData()

            self.skill_platform_sel.setCurrentText(platform)

            if self.skill_app_sel.findText(app) < 0:
                print("set custom app")
                self.skill_app_sel.setCurrentText(QApplication.translate("QComboBox", "Custom"))
                self.skillCustomAppNameEdit.setText(app)
                self.skillCustomAppLinkEdit.setText(applink)
            else:
                print("set menu app")
                self.skill_app_sel.setCurrentText(app)
                self.skillCustomActionEdit.setText("")

            if self.skill_site_sel.findText(site) < 0:
                self.skill_site_sel.setCurrentText(QApplication.translate("QComboBox", "Custom"))
                self.skillCustomSiteNameEdit.setText(site)
                self.skillCustomSiteLinkEdit.setText(sitelink)
            else:
                self.skill_site_sel.setCurrentText(site)
                self.skillCustomActionEdit.setText("")


            if self.skill_action_sel.findText(action) < 0:
                self.skill_action_sel.setCurrentText(QApplication.translate("QComboBox", "Custom"))
                self.skillCustomActionEdit.setText(action)
            else:
                self.skill_action_sel.setCurrentText(action)
                self.skillCustomActionEdit.setText("")

    def genNewTicket(self):
        # get a new ticket using parent's DB connection.
        print("new ticket number is: ")

    def buildSkillSelList(self):
        for sk in self.parent.skills:
            self.skill_action_sel.addItem(QApplication.translate("QComboBox", sk.getPlatform()+"_"+sk.getApp()+"_"+sk.getSiteName()+"_"+sk.getPage()+"_"+sk.getName()))


    def buy_rb_checked_state_changed(self):
        if self.buy_rb.isChecked():
            print("buy mission is selected....")
            self.show_buy_attributes()
            self.hide_sell_attributes()
        else:
            self.show_sell_attributes()
            self.hide_buy_attributes()

    def show_buy_attributes(self):
        self.pseudo_store_label.setVisible(True)
        self.pseudo_store_edit.setVisible(True)
        self.pseudo_brand_label.setVisible(True)
        self.pseudo_brand_edit.setVisible(True)
        self.pseudo_asin_label.setVisible(True)
        self.pseudo_asin_edit.setVisible(True)
        self.seller_label.setVisible(True)
        self.seller_edit.setVisible(True)
        self.rating_label.setVisible(True)
        self.rating_edit.setVisible(True)
        self.feedbacks_label.setVisible(True)
        self.feedbacks_edit.setVisible(True)
        self.price_label.setVisible(True)
        self.price_edit.setVisible(True)
        self.title_label.setVisible(True)
        self.title_edit.setVisible(True)
        self.search_kw_label.setVisible(True)
        self.search_kw_edit.setVisible(True)
        self.search_cat_label.setVisible(True)
        self.search_cat_edit.setVisible(True)
        self.buy_mission_type_label.setVisible(True)
        self.buy_mission_type_sel.setVisible(True)
        self.asin_label.setVisible(True)
        self.asin_edit.setVisible(True)
        self.product_image_label.setVisible(True)
        self.product_image_edit.setVisible(True)
        self.bought_label.setVisible(True)
        self.bought_cb.setVisible(True)
        self.received_label.setVisible(True)
        self.received_cb.setVisible(True)
        self.fb_rated_label.setVisible(True)
        self.fb_rated_cb.setVisible(True)
        self.fb_reviewed_label.setVisible(True)
        self.fb_reviewed_cb.setVisible(True)

    def hide_buy_attributes(self):
        self.pseudo_store_label.setVisible(False)
        self.pseudo_store_edit.setVisible(False)
        self.pseudo_brand_label.setVisible(False)
        self.pseudo_brand_edit.setVisible(False)
        self.pseudo_asin_label.setVisible(False)
        self.pseudo_asin_edit.setVisible(False)
        self.seller_label.setVisible(False)
        self.seller_edit.setVisible(False)
        self.rating_label.setVisible(False)
        self.rating_edit.setVisible(False)
        self.feedbacks_label.setVisible(False)
        self.feedbacks_edit.setVisible(False)
        self.price_label.setVisible(False)
        self.price_edit.setVisible(False)
        self.title_label.setVisible(False)
        self.title_edit.setVisible(False)
        self.search_kw_label.setVisible(False)
        self.search_kw_edit.setVisible(False)
        self.search_cat_label.setVisible(False)
        self.search_cat_edit.setVisible(False)
        self.buy_mission_type_label.setVisible(False)
        self.buy_mission_type_sel.setVisible(False)
        self.asin_label.setVisible(False)
        self.asin_edit.setVisible(False)
        self.product_image_label.setVisible(False)
        self.product_image_edit.setVisible(False)
        self.bought_label.setVisible(False)
        self.bought_cb.setVisible(False)
        self.received_label.setVisible(False)
        self.received_cb.setVisible(False)
        self.fb_rated_label.setVisible(False)
        self.fb_rated_cb.setVisible(False)
        self.fb_reviewed_label.setVisible(False)
        self.fb_reviewed_cb.setVisible(False)

    def show_sell_attributes(self):
        self.sell_mission_type_label.setVisible(True)
        self.sell_mission_type_sel.setVisible(True)

    def hide_sell_attributes(self):
        self.sell_mission_type_label.setVisible(False)
        self.sell_mission_type_sel.setVisible(False)
