import sys
import random

from PySide6.QtCore import QEvent, QStringListModel
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QMainWindow, QTabWidget, QVBoxLayout, QLineEdit, \
    QCompleter, QComboBox, QScrollArea, QHBoxLayout, QRadioButton, QCheckBox, QFileDialog
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
                self.parent.updateSelectedSkill(self.selected_row)



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


class MissionNewWin(QMainWindow):
    def __init__(self, parent):
        super(MissionNewWin, self).__init__(parent)

        self.text = QApplication.translate("QMainWindow", "new mission")
        self.parent = parent
        self.homepath = parent.homepath
        self.newMission = None
        self.owner = None

        self.selected_skill_row = None
        self.selected_skill_item = None

        self.selected_skill_platform = "Windows"
        self.selected_skill_app = "Chrome"
        self.selected_skill_app_link = ""
        self.selected_skill_site = "Amazon"
        self.selected_skill_site_link = ""
        self.selected_skill_action = "Browse"

        self.mainWidget = QWidget()
        self.tabs = QTabWidget()
        self.pubAttrWidget = QWidget()
        self.prvAttrWidget = QWidget()
        self.actItemsWidget = QWidget()

        self.skillPanel = QFrame()
        self.skillPanelLayout = QVBoxLayout(self)

        self.skillListView = SkillListView(self)
        self.skillListView.installEventFilter(self)


        self.skillModel = QStandardItemModel(self.skillListView)

        self.skillListView.setModel(self.skillModel)
        self.skillListView.setViewMode(QListView.IconMode)
        self.skillListView.setMovement(QListView.Snap)

        QApplication.translate("QLabel", "Skill Platform:")
        self.skillNameLabel = QLabel(QApplication.translate("QLabel", "Skill Name:"), alignment=Qt.AlignLeft)
        self.skillNameEdit = QLineEdit("")
        self.skillNameList = QStringListModel()
        self.skillNameCompleter = QCompleter(self.skillNameList, self)
        self.skillNameCompleter.setCaseSensitivity(Qt.CaseInsensitive)
        self.skillNameEdit.setCompleter(self.skillNameCompleter)

        self.skillPlatformLabel = QLabel(QApplication.translate("QLabel", "Skill Platform:"), alignment=Qt.AlignLeft)
        self.skill_platform_sel = QComboBox()
        self.skill_platform_sel.addItem(QApplication.translate("QComboBox", "Windows"))
        self.skill_platform_sel.addItem(QApplication.translate("QComboBox", "Mac"))
        self.skill_platform_sel.addItem(QApplication.translate("QComboBox", "Linux"))
        self.skill_platform_sel.currentTextChanged.connect(self.skillPlatformSel_changed)


        self.skillAppLabel = QLabel(QApplication.translate("QLabel", "Skill App:"), alignment=Qt.AlignLeft)
        self.skill_app_sel = QComboBox()
        self.skill_app_sel.addItem(QApplication.translate("QComboBox", "Chrome"))
        self.skill_app_sel.addItem(QApplication.translate("QComboBox", "ADS Power"))
        self.skill_app_sel.addItem(QApplication.translate("QComboBox", "Multi-Login"))
        self.skill_app_sel.addItem(QApplication.translate("QComboBox", "FireFox"))
        self.skill_app_sel.addItem(QApplication.translate("QComboBox", "Edge"))
        self.skill_app_sel.addItem(QApplication.translate("QComboBox", "Custom"))
        self.skill_app_sel.currentTextChanged.connect(self.skillAppSel_changed)

        QApplication.translate("QLabel", "Skill Site:")
        self.skillCustomAppNameLabel = QLabel(QApplication.translate("QLabel", "Custome App:"), alignment=Qt.AlignLeft)
        self.skillCustomAppNameEdit = QLineEdit("")

        self.skillCustomAppLinkLabel = QLabel(QApplication.translate("QLabel", "Custome App Path:"), alignment=Qt.AlignLeft)
        self.skillCustomAppLinkEdit = QLineEdit("")
        self.skillCustomAppLinkButton = QPushButton("...")
        self.skillCustomAppLinkButton.clicked.connect(self.chooseAppLinkDir)

        self.skillSiteLabel = QLabel(QApplication.translate("QLabel", "Skill Site:"), alignment=Qt.AlignLeft)
        self.skill_site_sel = QComboBox()

        self.skill_site_sel.addItem(QApplication.translate("QComboBox", "Amazon"))

        self.skill_site_sel.addItem(QApplication.translate("QComboBox", "Ebay"))
        self.skill_site_sel.addItem(QApplication.translate("QComboBox", "Etsy"))
        self.skill_site_sel.addItem(QApplication.translate("QComboBox", "Walmart"))
        self.skill_site_sel.addItem(QApplication.translate("QComboBox", "Wish"))
        self.skill_site_sel.addItem(QApplication.translate("QComboBox", "AliExpress"))
        self.skill_site_sel.addItem(QApplication.translate("QComboBox", "Wayfair"))
        self.skill_site_sel.addItem(QApplication.translate("QComboBox", "Custom"))
        self.skill_site_sel.currentTextChanged.connect(self.skillSiteSel_changed)

        self.skillCustomSiteNameLabel = QLabel(QApplication.translate("QLabel", "Custom Site:"), alignment=Qt.AlignLeft)
        self.skillCustomSiteNameEdit = QLineEdit("")
        self.skillCustomSiteLinkLabel = QLabel(QApplication.translate("QLabel", "Custom Site Html:"), alignment=Qt.AlignLeft)
        self.skillCustomSiteLinkEdit = QLineEdit("")

        self.skillActionLabel = QLabel(QApplication.translate("QLabel", "Skill Action:"), alignment=Qt.AlignLeft)
        self.skill_action_sel = QComboBox()

        self.skill_action_sel.addItem(QApplication.translate("QComboBox", "BuyOnly"))
        self.skill_action_sel.addItem(QApplication.translate("QComboBox", "BuyWithPositiveFeedback"))
        self.skill_action_sel.addItem(QApplication.translate("QComboBox", "Browse"))
        self.skill_action_sel.addItem(QApplication.translate("QComboBox", "ManageOffers"))
        self.skill_action_sel.addItem(QApplication.translate("QComboBox", "ManageReturnRequest"))
        self.skill_action_sel.addItem(QApplication.translate("QComboBox", "BuyShippingLabel"))
        self.skill_action_sel.addItem(QApplication.translate("QComboBox", "FillShippingTracking"))
        self.skill_action_sel.addItem(QApplication.translate("QComboBox", "ManageReplacements"))
        self.skill_action_sel.addItem(QApplication.translate("QComboBox", "ManageRefund"))
        self.skill_action_sel.addItem(QApplication.translate("QComboBox", "Custom"))
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
        self.sell_rb = QRadioButton(QApplication.translate("QPushButton", "Sell Side"))
        self.buy_rb.isChecked()

        self.mission_auto_assign_label = QLabel(QApplication.translate("QLabel", "Assignment Type:"), alignment=Qt.AlignLeft)
        self.manual_rb = QRadioButton(QApplication.translate("QPushButton", "Manual Assign(Bot and Schedule)"))
        self.auto_rb = QRadioButton(QApplication.translate("QPushButton", "Auto Assign(Bot and Schedule)"))
        self.auto_rb.isChecked()

        self.bid_label = QLabel(QApplication.translate("QLabel", "Assigned Bot ID:"), alignment=Qt.AlignLeft)
        self.bid_edit = QLineEdit()
        self.ert_label = QLabel(QApplication.translate("QLabel", "Estimated Duration Time(Sec):"), alignment=Qt.AlignLeft)
        self.ert_edit = QLineEdit()
        self.est_label = QLabel(QApplication.translate("QLabel", "Estimated Start Time(hh:mm:ss):"), alignment=Qt.AlignLeft)
        self.est_edit = QLineEdit()

        self.buy_mission_type_label = QLabel(QApplication.translate("QLabel", "Buy Mission Type:"), alignment=Qt.AlignLeft)
        self.buy_mission_type_sel = QComboBox()

        self.buy_mission_type_sel.addItem(QApplication.translate("QComboBox", "Simple Buy"))
        self.buy_mission_type_sel.addItem(QApplication.translate("QComboBox", "Feedback Rating"))
        self.buy_mission_type_sel.addItem(QApplication.translate("QComboBox", "Review"))

        self.sell_mission_type_label = QLabel(QApplication.translate("QLabel", "Sell Mission Type:"), alignment=Qt.AlignLeft)
        self.sell_mission_type_sel = QComboBox()

        self.sell_mission_type_sel.addItem(QApplication.translate("QComboBox", "Prepare Shipping Label"))
        self.sell_mission_type_sel.addItem(QApplication.translate("QComboBox", "Check Inventory"))
        self.sell_mission_type_sel.addItem(QApplication.translate("QComboBox", "Process Messages"))
        self.sell_mission_type_sel.addItem(QApplication.translate("QComboBox", "Handle Return"))
        self.sell_mission_type_sel.addItem(QApplication.translate("QComboBox", "Handle Replacement"))
        self.sell_mission_type_sel.addItem(QApplication.translate("QComboBox", "Handle Marketing"))
        self.sell_mission_type_sel.addItem(QApplication.translate("QComboBox", "Custom Work"))
        self.sell_mission_type_sel.addItem(QApplication.translate("QComboBox", "Other"))

        self.repeat_label = QLabel(QApplication.translate("QLabel", "Repeat every:"), alignment=Qt.AlignLeft)
        self.repeat_edit = QLineEdit()
        self.repeat_edit.setPlaceholderText("1")

        self.repeat_interval_label = QLabel(QApplication.translate("QLabel", " "), alignment=Qt.AlignLeft)
        self.repeat_interval_sel = QComboBox()

        self.repeat_interval_sel.addItem(QApplication.translate("QComboBox", "Day(s)"))
        self.repeat_interval_sel.addItem(QApplication.translate("QComboBox", "Week(s)"))
        self.repeat_interval_sel.addItem(QApplication.translate("QComboBox", "Month(s)"))
        self.repeat_interval_sel.addItem(QApplication.translate("QComboBox", "Year(s)"))
        self.repeat_interval_sel.addItem(QApplication.translate("QComboBox", "Hour(s)"))
        self.repeat_interval_sel.addItem(QApplication.translate("QComboBox", "Minute(s)"))

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

        self.pubAttrLine2Layout = QHBoxLayout(self)
        self.pubAttrLine2Layout.addWidget(self.mission_type_label)
        self.pubAttrLine2Layout.addWidget(self.buy_rb)
        self.pubAttrLine2Layout.addWidget(self.sell_rb)
        self.pubAttrWidget.layout.addLayout(self.pubAttrLine2Layout)

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
        self.pubAttrLine3Layout.addWidget(self.repeat_interval_label)
        self.pubAttrLine3Layout.addWidget(self.repeat_interval_sel)
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
        self.pubpflLine9Layout.addWidget(self.skillPlatformLabel)
        self.pubpflLine9Layout.addWidget(self.skill_platform_sel)
        self.pubpflLine9Layout.addWidget(self.skillAppLabel)
        self.pubpflLine9Layout.addWidget(self.skill_app_sel)
        self.pubpflLine9Layout.addWidget(self.skillSiteLabel)
        self.pubpflLine9Layout.addWidget(self.skill_site_sel)
        self.pubpflLine9Layout.addWidget(self.skillActionLabel)
        self.pubpflLine9Layout.addWidget(self.skill_action_sel)
        self.skillPanelLayout.addLayout(self.pubpflLine9Layout)


        self.pubpflLine11Layout = QHBoxLayout(self)
        self.pubpflLine11Layout.addWidget(self.skillCustomAppNameLabel)
        self.pubpflLine11Layout.addWidget(self.skillCustomAppNameEdit)
        self.pubpflLine11Layout.addWidget(self.skillCustomAppLinkLabel)
        self.pubpflLine11Layout.addWidget(self.skillCustomAppLinkEdit)
        self.skillPanelLayout.addLayout(self.pubpflLine11Layout)

        self.pubpflLine12Layout = QHBoxLayout(self)
        self.pubpflLine12Layout.addWidget(self.skillCustomSiteNameLabel)
        self.pubpflLine12Layout.addWidget(self.skillCustomSiteNameEdit)
        self.pubpflLine12Layout.addWidget(self.skillCustomSiteLinkLabel)
        self.pubpflLine12Layout.addWidget(self.skillCustomSiteLinkEdit)
        self.skillPanelLayout.addLayout(self.pubpflLine12Layout)

        self.pubpflLine13Layout = QHBoxLayout(self)
        self.pubpflLine13Layout.addWidget(self.skillCustomActionLabel)
        self.pubpflLine13Layout.addWidget(self.skillCustomActionEdit)
        self.skillPanelLayout.addLayout(self.pubpflLine13Layout)

        self.hide_skill_custom_app()
        self.hide_skill_custom_site()
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
        self.cus_alt_sm_type_sel.addItem(QApplication.translate("QComboBox", "QQ"))
        self.cus_alt_sm_type_sel.addItem(QApplication.translate("QComboBox", "Wechat"))
        self.cus_alt_sm_type_sel.addItem(QApplication.translate("QComboBox", "Telegram"))
        self.cus_alt_sm_type_sel.addItem(QApplication.translate("QComboBox", "WhatsApp"))
        self.cus_alt_sm_type_sel.addItem(QApplication.translate("QComboBox", "Messenger"))
        self.cus_alt_sm_type_sel.addItem(QApplication.translate("QComboBox", "Other"))

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

    def saveMission(self):
        print("saving bot....")
        # if this bot already exists, then, this is an update case, else this is a new bot creation case.
        self.newMission = EBMISSION(self.parent)


        if self.repeat_edit.text().isnumeric():
            self.newMission.pubAttributes.setNex(int(self.repeat_edit.text()))
        self.newMission.pubAttributes.setSearch(self.search_kw_edit.text(), self.search_cat_edit.text())
        if self.buy_rb.isChecked():
            self.newMission.pubAttributes.setType(0, "user", "Sell")
        elif self.sell_rb.isChecked():
            self.newMission.pubAttributes.setType(0, "user", "Buy")
        else:
            self.newMission.pubAttributes.setType(0, "user", "NA")

        self.newMission.privateAttributes.setFbType(self.buy_mission_type_sel.currentText())
        self.newMission.privateAttributes.setItem(self.asin_edit.text(), self.seller_edit.text(), self.title_edit.text(), self.product_image_edit.text(), self.rating_edit.text())

        print("adding new mission....")
        self.parent.addNewMission(self.newMission)
        self.close()


    def selFile(self):
        # File actions
        fdir = self.fsel.getExistingDirectory()
        print(fdir)
        return fdir

    def setOwner(self, owner):
        self.owner = owner

    def setMission(self, mission):
        self.newMission = mission


    def skillPlatformSel_changed(self):
        self.selected_skill_platform = self.skill_platform_sel.currentText()


    def skillAppSel_changed(self):
        print("app changed....")
        if self.skill_app_sel.currentText() != 'Custom':
            self.hide_skill_custom_app()
            self.selected_skill_app = self.skill_app_sel.currentText()
            self.selected_skill_app_link = ""

        else:
            self.show_skill_custom_app()
            self.selected_skill_app = self.skillCustomAppNameEdit.text()
            self.selected_skill_app_link = self.skillCustomAppLinkEdit.text()

    def skillSiteSel_changed(self):
        if self.skill_site_sel.currentText() != 'Custom':
            self.hide_skill_custom_site()
            self.selected_skill_site = self.skill_site_sel.currentText()
            self.selected_skill_site_link = ""

        else:
            self.show_skill_custom_site()
            self.selected_skill_site = self.skillCustomSiteNameEdit.text()
            self.selected_skill_site_link = self.skillCustomSiteLinkEdit.text()

    def skillActionSel_changed(self):
        if self.skill_action_sel.currentText() != 'Custom':
            self.hide_skill_custom_action()
            self.selected_skill_action = self.skill_action_sel.currentText()
        else:
            self.show_skill_custom_action()
            self.selected_skill_action = self.skillCustomActionEdit.text()




    def hide_skill_custom_app(self):
        self.skillCustomAppNameLabel.setVisible(False)
        self.skillCustomAppNameEdit.setVisible(False)
        self.skillCustomAppLinkLabel.setVisible(False)
        self.skillCustomAppLinkEdit.setVisible(False)

    def show_skill_custom_app(self):
        self.skillCustomAppNameLabel.setVisible(True)
        self.skillCustomAppNameEdit.setVisible(True)
        self.skillCustomAppLinkLabel.setVisible(True)
        self.skillCustomAppLinkEdit.setVisible(True)


    def hide_skill_custom_site(self):
        self.skillCustomSiteNameLabel.setVisible(False)
        self.skillCustomSiteNameEdit.setVisible(False)
        self.skillCustomSiteLinkLabel.setVisible(False)
        self.skillCustomSiteLinkEdit.setVisible(False)


    def show_skill_custom_site(self):
        self.skillCustomSiteNameLabel.setVisible(True)
        self.skillCustomSiteNameEdit.setVisible(True)
        self.skillCustomSiteLinkLabel.setVisible(True)
        self.skillCustomSiteLinkEdit.setVisible(True)

    def hide_skill_custom_action(self):
        self.skillCustomActionLabel.setVisible(False)
        self.skillCustomActionEdit.setVisible(False)

    def show_skill_custom_action(self):
        self.skillCustomActionLabel.setVisible(True)
        self.skillCustomActionEdit.setVisible(True)

    def chooseAppLinkDir(self):
        self.skillCustomAppLinkEdit.setText(str(QFileDialog.getExistingDirectory(self, "Select Directory")))
        self.selected_skill_app_link = self.skillCustomAppLinkEdit.text()

    def addSkill(self):
        if self.skill_app_sel.currentText() == 'Custom':
            self.selected_skill_app = self.skillCustomAppNameEdit.text()
            self.selected_skill_app_link = self.skillCustomAppLinkEdit.text()

        if self.skill_site_sel.currentText() == 'Custom':
            self.selected_skill_site = self.skillCustomSiteNameEdit.text()
            self.selected_skill_site_link = self.skillCustomSiteLinkEdit.text()

        if self.skill_action_sel.currentText() == 'Custom':
            self.selected_skill_action = self.skillCustomActionEdit.text()

        self.newSKILL = MWORKSKILL(self.homepath, self.selected_skill_platform, self.selected_skill_app, self.selected_skill_app_link, self.selected_skill_site, self.selected_skill_site_link, self.selected_skill_action)
        self.skillModel.appendRow(self.newSKILL)

    def removeSkill(self):
        self.skillModel.removeRow(self.selected_skill_item.row())


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